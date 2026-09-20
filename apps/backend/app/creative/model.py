"""The creative director. Provider-neutral interface + the DeepSeek implementation (OpenAI-compatible chat API)."""
import logging
import os
import ssl
import time

import httpx
from pydantic import BaseModel, ValidationError

from app import config, settings
from app.creative import prompts
from app.creative.schemas import BatchPlan, PieceContent, PlanItem
from app.errors import UserError

log = logging.getLogger("creative")


class CreativeModel:
    """PRD §7: providers are swappable. Implementations return validated schema objects or raise UserError."""

    def plan_batch(self, brief: dict, avoid: list[str]) -> BatchPlan: ...

    def write_piece(self, brief: dict, plan: BatchPlan, item: PlanItem, avoid: list[str]) -> PieceContent: ...


class DeepSeekModel(CreativeModel):
    URL = os.environ.get("ACS_DEEPSEEK_URL", "https://api.deepseek.com") + "/chat/completions"  # env: tests/proxies
    RETRIES = 3  # PRD §79: API calls, exponential backoff

    def __init__(self, api_key: str, model: str, temperature: float, max_tokens: int, transport=None):
        self.model, self.temperature, self.max_tokens = model, temperature, max_tokens
        # Windows cert store via the stdlib context: works behind TLS-inspecting local CAs where certifi doesn't.
        self.http = httpx.Client(headers={"Authorization": f"Bearer {api_key}"}, timeout=httpx.Timeout(120, connect=15),
                                 verify=ssl.create_default_context(), transport=transport)

    def plan_batch(self, brief, avoid):
        plan = self._json(prompts.plan(brief, avoid), BatchPlan)
        if len(plan.pieces) != brief["quantity"]:
            raise UserError("DeepSeek returned a plan with the wrong number of pieces.",
                            f"asked {brief['quantity']}, got {len(plan.pieces)}")
        return plan

    def write_piece(self, brief, plan, item, avoid):
        return self._json(prompts.piece(brief, plan, item, avoid), PieceContent)

    def _json(self, messages: list[dict], schema: type[BaseModel]):
        """Call, validate; if invalid, ask the model to repair once; if still invalid, regenerate once (PRD §100)."""
        attempts = [messages, None, messages]
        last = ""
        for i, msgs in enumerate(attempts):
            if msgs is None:  # repair round: show the model its own output and the validation error
                msgs = messages + [{"role": "assistant", "content": text},
                                   {"role": "user", "content": prompts.repair(last)}]
            text = self._chat(msgs)
            try:
                return schema.model_validate_json(text)
            except ValidationError as e:
                last = str(e)
                log.warning("invalid %s from model (attempt %d): %s", schema.__name__, i + 1, last[:300])
        raise UserError("DeepSeek kept returning content in the wrong shape.", last)

    def _chat(self, messages: list[dict]) -> str:
        body = {"model": self.model, "messages": messages, "temperature": self.temperature,
                "max_tokens": self.max_tokens, "response_format": {"type": "json_object"}}
        for attempt in range(self.RETRIES + 1):
            try:
                r = self.http.post(self.URL, json=body)
            except httpx.HTTPError as e:
                if attempt == self.RETRIES:
                    raise UserError("Couldn't reach DeepSeek. Check your internet connection.", repr(e))
            else:
                if r.status_code == 401:
                    raise UserError("DeepSeek authentication failed. Check your DeepSeek API key in Settings.", r.text[:500])
                if r.status_code == 402:
                    raise UserError("Your DeepSeek account is out of balance. Top it up, then try again.", r.text[:500])
                if r.status_code in (400, 422):
                    raise UserError("DeepSeek rejected the request. Check the model name in Settings.", r.text[:500])
                if r.is_success:
                    reply = r.json()
                    choice = reply["choices"][0]
                    content = (choice["message"].get("content") or "").strip()
                    # Out of output room: the JSON is cut mid-string. Repairing or retrying just truncates again,
                    # and reasoning-capable models spend this budget before they emit a single visible character.
                    if choice.get("finish_reason") == "length":
                        raise UserError(
                            "The AI ran out of room before it finished writing. Raise \"AI max tokens\" in "
                            "Settings, then try again.",
                            f"finish_reason=length, usage={reply.get('usage')}, max_tokens={self.max_tokens}")
                    if content:  # JSON mode occasionally returns empty content: retry
                        return content
                elif attempt == self.RETRIES:
                    raise UserError("DeepSeek is having trouble right now. Try again in a few minutes.",
                                    f"HTTP {r.status_code}: {r.text[:500]}")
            if attempt < self.RETRIES:
                time.sleep(2 ** attempt)
        raise UserError("DeepSeek returned empty responses.", "empty content after retries")


def get_model() -> CreativeModel:
    key = config.SECRETS.get("DEEPSEEK_API_KEY")
    if not key:
        raise UserError("Add your DeepSeek API key in Settings to generate content.")
    s = settings.get()
    return DeepSeekModel(key, s["ai_model"], s["ai_temperature"], s["ai_max_tokens"])
