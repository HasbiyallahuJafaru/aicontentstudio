"""The video host Buffer publishes from. Buffer's API has no upload endpoint — it fetches each post's video
from a public https URL — so the user points the app at their own S3-compatible bucket (Cloudflare R2 works)
and each published clip is PUT there under an unguessable name. Upload auth is a hand-rolled AWS SigV4 for a
single PUT: ~40 lines instead of a boto3 dependency."""
import hashlib
import hmac
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app import settings
from app.errors import UserError
from app.publish import store

REGION_DEFAULT = "auto"  # Cloudflare R2's region; real AWS regions work the same way
SERVICE = "s3"


def configured() -> bool:
    s = settings.get()
    return bool(s["publish_host_endpoint"] and s["publish_host_bucket"]
                and s["publish_host_public_url"] and store.load("publish_host"))


def save(endpoint: str, bucket: str, public_url: str, region: str,
         access_key_id: str, secret_access_key: str) -> dict:
    """Settings (non-secret) go in the settings row; the keys are DPAPI-encrypted like the other credentials.
    Blank keys keep the ones already stored."""
    settings.update(publish_host_endpoint=endpoint.strip(), publish_host_bucket=bucket.strip(),
                    publish_host_public_url=public_url.strip(), publish_host_region=region.strip() or REGION_DEFAULT)
    if access_key_id and secret_access_key:
        store.save("publish_host", {"access_key_id": access_key_id.strip(),
                                    "secret_access_key": secret_access_key.strip()})
    elif not store.load("publish_host"):
        raise UserError("Paste the host's access key id and secret access key.")
    return status()


def status() -> dict:
    s = settings.get()
    return {"endpoint": s["publish_host_endpoint"], "bucket": s["publish_host_bucket"],
            "public_url": s["publish_host_public_url"], "region": s["publish_host_region"],
            "keys_set": store.load("publish_host") is not None, "configured": configured()}


def upload(path: Path, name: str) -> str:
    """PUT the file as {endpoint}/{bucket}/{name} and return its public URL. The URL must stay live until the
    post goes out — deleting uploaded copies is the user's call (their bucket, their lifecycle rules)."""
    s = settings.get()
    endpoint, bucket = s["publish_host_endpoint"].rstrip("/"), s["publish_host_bucket"]
    public = s["publish_host_public_url"].rstrip("/")
    keys = store.load("publish_host")
    if not (endpoint and bucket and public and keys):
        raise UserError("Publishing needs somewhere public to host the video. Add an S3-compatible bucket "
                        "(Cloudflare R2 works) under Settings, Publishing.")
    url = f"{endpoint}/{bucket}/{name}"
    with open(path, "rb") as f:
        payload = f.read()
    headers = _sigv4_headers("PUT", f"/{bucket}/{name}", s["publish_host_endpoint"], payload,
                             keys["access_key_id"], keys["secret_access_key"], s["publish_host_region"])
    try:
        r = httpx.put(url, content=payload, headers=headers, timeout=300)
    except httpx.HTTPError as e:
        raise UserError("Couldn't reach the media host. Try again in a minute.", repr(e)) from e
    if not r.is_success:
        raise UserError("The media host refused the video upload.", f"HTTP {r.status_code}: {r.text[:300]}")
    return f"{public}/{name}"


def _sigv4_headers(method: str, path: str, endpoint: str, payload: bytes, access_key: str, secret_key: str,
                   region: str) -> dict:
    now = datetime.now(timezone.utc)
    amz_date, datestamp = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    host = httpx.URL(endpoint).host
    payload_hash = hashlib.sha256(payload).hexdigest()
    signed = "host;x-amz-content-sha256;x-amz-date"
    canonical = "\n".join([method, path, "", f"host:{host}",
                           f"x-amz-content-sha256:{payload_hash}", f"x-amz-date:{amz_date}",
                           "", signed, payload_hash])
    scope = f"{datestamp}/{region}/{SERVICE}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    k = _sign_key(secret_key, datestamp, region)
    signature = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()
    return {"x-amz-content-sha256": payload_hash, "x-amz-date": amz_date,
            "Authorization": (f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
                              f"SignedHeaders={signed}, Signature={signature}")}


def _sign_key(secret: str, datestamp: str, region: str) -> bytes:
    step = hmac.new(f"AWS4{secret}".encode(), datestamp.encode(), hashlib.sha256).digest()
    step = hmac.new(step, region.encode(), hashlib.sha256).digest()
    step = hmac.new(step, SERVICE.encode(), hashlib.sha256).digest()
    return hmac.new(step, b"aws4_request", hashlib.sha256).digest()
