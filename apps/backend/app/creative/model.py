"""The creative director. Provider-neutral interface + the OpenRouter implementation (OpenAI-compatible chat API).
One OpenRouter key covers every model call in the app: writing, clip selection (here) and transcription
(app/clipper/transcribe.py)."""
import json
import logging
import os
import ssl
import time

import httpx
from pydantic import BaseModel, ValidationError

from app import config, settings
from app.creative import prompts
from app.creative.schemas import BatchPlan, PieceContent, PlanItem, VideoPieceContent
from app.errors import UserError

log = logging.getLogger("creative")

BASE = os.environ.get("ACS_OPENROUTER_URL", "https://openrouter.ai/api/v1")  # env: tests/proxies


def api_key(action: str) -> str:
    key = config.SECRETS.get("OPENROUTER_API_KEY")
    if not key:
        raise UserError(f"Add your OpenRouter API key in Settings to {action}.")
    return key


class CreativeModel:
    """PRD §7: providers are swappable. Implementations return validated schema objects or raise UserError."""

    def plan_batch(self, brief: dict, avoid: list[str]) -> BatchPlan: ...

    def write_piece(self, brief: dict, plan: BatchPlan, item: PlanItem, avoid: list[str]) -> PieceContent: ...

    def verify_quotes(self, quotes: list[tuple[str, str]]) -> list[str]:
        """"yes" | "no" | "unsure" per (text, author). The default can't check, so it says nothing against them."""
        return ["unsure"] * len(quotes)

    def write_pieces(self, brief: dict, plan: BatchPlan, items: list[PlanItem], avoid: list[str],
                     given: list) -> list[PieceContent | None]:
        """Several pieces at once. This default writes them one by one; OpenRouterModel asks in one request. A None
        means that piece came back unusable and the caller writes it on its own."""
        out = []
        for item, own in zip(items, given):
            b = {**brief, "given_quote": own[0], "given_author": own[1]} if own else brief
            out.append(self.write_piece(b, plan, item, avoid))
        return out


class OutOfRoom(UserError):
    """The reply hit max_tokens mid-JSON (a reasoning model spends the budget thinking). A group write survives it
    by writing its pieces one at a time; a single piece can't, so its message says which setting to raise."""


class OpenRouterModel(CreativeModel):
    URL = BASE + "/chat/completions"
    RETRIES = 3  # PRD §79: API calls, exponential backoff

    def __init__(self, api_key: str, model: str, temperature: float, max_tokens: int, transport=None,
                 fast_model: str | None = None):
        self.model, self.temperature, self.max_tokens = model, temperature, max_tokens
        self.fast_model = fast_model or model
        # Windows cert store via the stdlib context: works behind TLS-inspecting local CAs where certifi doesn't.
        self.http = httpx.Client(headers={"Authorization": f"Bearer {api_key}"}, timeout=httpx.Timeout(120, connect=15),
                                 verify=ssl.create_default_context(), transport=transport)

    def plan_batch(self, brief, avoid):
        plan = self._json(prompts.plan(brief, avoid), BatchPlan)
        if len(plan.pieces) != brief["quantity"]:
            raise UserError("The AI returned a plan with the wrong number of pieces.",
                            f"asked {brief['quantity']}, got {len(plan.pieces)}")
        return plan

    def write_piece(self, brief, plan, item, avoid):
        schema = PieceContent if prompts.quotes_only(brief) else VideoPieceContent
        return self._json(prompts.piece(brief, plan, item, avoid), schema)

    def write_pieces(self, brief, plan, items, avoid, given):
        """One request for the whole group; each piece is validated on its own, so one malformed piece costs only
        that piece (returned as None) and never the batch."""
        schema = PieceContent if prompts.quotes_only(brief) else VideoPieceContent
        try:
            found = json.loads(self._chat(prompts.pieces(brief, plan, items, avoid, given))).get("pieces") or []
        except (ValueError, AttributeError, OutOfRoom) as e:  # a group too big for the reply: write each alone
            log.warning("batch write returned no usable JSON: %s", e)
            found = []
        out = []
        for j in range(len(items)):
            try:
                out.append(schema.model_validate(found[j]) if j < len(found) else None)
            except ValidationError as e:
                log.warning("batch piece %d invalid: %s", j + 1, str(e)[:300])
                out.append(None)
        return out

    def verify_quotes(self, quotes):
        """One call on the fast model for the whole batch. Fails open (all "unsure"): a check that can't run must
        not stop a generation. ponytail: only "no" is acted on; "unsure" passes, tighten if fakes slip through."""
        if not quotes:
            return []
        try:
            got = json.loads(self._chat(prompts.verify(quotes), model=self.fast_model, temperature=0)).get("verdicts")
        except (UserError, ValueError, AttributeError) as e:
            log.warning("quote check skipped: %s", e)
            return ["unsure"] * len(quotes)
        got = [str(v).lower() for v in got] if isinstance(got, list) else []
        return got[:len(quotes)] + ["unsure"] * (len(quotes) - len(got))

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
        raise UserError("The AI kept returning content in the wrong shape.", last)

    def _chat(self, messages: list[dict], model: str | None = None, temperature: float | None = None) -> str:
        body = {"model": model or self.model, "messages": messages,
                "temperature": self.temperature if temperature is None else temperature,
                "max_tokens": self.max_tokens, "response_format": {"type": "json_object"},
                # only route to providers that honour JSON mode: without it a provider may ignore response_format
                "provider": {"require_parameters": True}}
        for attempt in range(self.RETRIES + 1):
            try:
                r = self.http.post(self.URL, json=body)
            except httpx.HTTPError as e:
                if attempt == self.RETRIES:
                    raise UserError("Couldn't reach OpenRouter. Check your internet connection.", repr(e))
            else:
                if r.status_code == 401:
                    raise UserError("OpenRouter authentication failed. Check your OpenRouter API key in Settings.", r.text[:500])
                if r.status_code == 402:
                    raise UserError("Your OpenRouter account is out of credits. Top it up, then try again.", r.text[:500])
                if r.status_code in (400, 404, 422):
                    raise UserError("OpenRouter rejected the request. Check the model names in Settings.", r.text[:500])
                if r.is_success:
                    reply = r.json()
                    choice = reply["choices"][0]
                    content = (choice["message"].get("content") or "").strip()
                    # Out of output room: the JSON is cut mid-string. Repairing or retrying just truncates again,
                    # and reasoning-capable models spend this budget before they emit a single visible character.
                    if choice.get("finish_reason") == "length":
                        raise OutOfRoom(
                            "The AI ran out of room before it finished writing. Raise \"AI max tokens\" in "
                            "Settings, then try again.",
                            f"finish_reason=length, usage={reply.get('usage')}, max_tokens={self.max_tokens}")
                    if content:  # JSON mode occasionally returns empty content: retry
                        return content
                elif attempt == self.RETRIES:
                    raise UserError("The AI service is having trouble right now. Try again in a few minutes.",
                                    f"HTTP {r.status_code}: {r.text[:500]}")
            if attempt < self.RETRIES:
                time.sleep(2 ** attempt)
        raise UserError("The AI returned empty responses.", "empty content after retries")


def get_model() -> CreativeModel:
    s = settings.get()
    return OpenRouterModel(api_key("generate content"), s["ai_model"], s["ai_temperature"], s["ai_max_tokens"],
                           fast_model=s["ai_model_fast"])
