"""Post teasers to TikTok via the Content Posting API."""

from __future__ import annotations

import secrets
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

from fugazy_publish.config import AppConfig, TikTokConfig
from fugazy_publish.http_retry import request_with_retry
from fugazy_publish.oauth_util import (
    cred_path,
    load_json,
    open_authorize_url,
    redirect_uri,
    save_json,
    tiktok_pkce_pair,
    token_expired,
    wait_for_oauth_code,
    with_expiry,
)

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
CREATOR_INFO_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
DIRECT_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
INBOX_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
CHUNK_BYTES = 10 * 1024 * 1024

# TikTok Content Posting API limits (per user access_token, official docs):
# - creator_info + video/init: 6 requests / minute
# - status/fetch: 30 requests / minute
# - inbox mode: max 5 pending (unpublished) inbox shares / 24 hours
# - direct post: ~15 posts / day / creator (varies by account)
RETRYABLE_ERROR_CODES = frozenset(
    {
        "rate_limit_exceeded",
        "spam_risk_too_many_pending_share",
        "spam_risk_too_many_posts",
    }
)


def _chunk_plan(video_size: int) -> tuple[int, int]:
    """Return (chunk_size, total_chunk_count) per TikTok media transfer rules."""
    if video_size < 5 * 1024 * 1024:
        return video_size, 1
    chunk_size = CHUNK_BYTES
    total_chunks = max(1, video_size // chunk_size)
    if total_chunks == 1:
        return video_size, 1
    return chunk_size, total_chunks


def _app(config: AppConfig) -> dict[str, str]:
    data = load_json(cred_path(config, "tiktok_app.json"))
    client_key = data.get("client_key") or data.get("client_id") or ""
    client_secret = data.get("client_secret") or ""
    if not client_key:
        raise FileNotFoundError(
            "Missing credentials/tiktok_app.json with client_key and client_secret. "
            "Register at https://developers.tiktok.com/ and run: py auth_social.py tiktok"
        )
    return {"client_key": str(client_key), "client_secret": str(client_secret)}


def _token_path(config: AppConfig) -> Path:
    return cred_path(config, "tiktok_token.json")


def _headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }


def _response_error_code(resp: requests.Response) -> str:
    try:
        payload = resp.json()
    except ValueError:
        return ""
    error = payload.get("error")
    if isinstance(error, dict):
        code = str(error.get("code", ""))
        return "" if code == "ok" else code
    if isinstance(error, str):
        return error
    return ""


def _post_publish_api(
    url: str,
    access_token: str,
    body: dict[str, Any],
    config: AppConfig,
    *,
    operation: str,
) -> dict[str, Any]:
    resp = request_with_retry(
        "POST",
        url,
        retry=config.retry,
        operation=operation,
        platform="TikTok",
        scope="tiktok_publish",
        throttle=True,
        headers=_headers(access_token),
        json=body,
        error_code_fn=_response_error_code,
        retryable_error_codes=RETRYABLE_ERROR_CODES,
        min_wait_by_code={"spam_risk_too_many_pending_share": 120.0},
    )
    code = _response_error_code(resp)
    if not resp.ok or code:
        raise RuntimeError(f"TikTok {operation} failed {resp.status_code}: {resp.text}")
    payload = resp.json()
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    return payload


def _refresh_token(config: AppConfig, token: dict[str, Any]) -> dict[str, Any]:
    app = _app(config)
    refresh = token.get("refresh_token")
    if not refresh:
        raise RuntimeError("TikTok token missing refresh_token; run: py auth_social.py tiktok")
    resp = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": app["client_key"],
            "client_secret": app["client_secret"],
            "grant_type": "refresh_token",
            "refresh_token": refresh,
        },
        timeout=60,
    )
    if not resp.ok:
        raise RuntimeError(f"TikTok token refresh failed {resp.status_code}: {resp.text}")
    payload = resp.json()
    merged = {
        **token,
        "access_token": payload["access_token"],
        "refresh_token": payload.get("refresh_token", refresh),
        "open_id": payload.get("open_id", token.get("open_id")),
        "scope": payload.get("scope", token.get("scope", "")),
    }
    if "expires_in" in payload:
        merged = with_expiry(merged, payload["expires_in"])
    save_json(_token_path(config), merged)
    return merged


def get_access_token(config: AppConfig) -> str:
    token = load_json(_token_path(config))
    access = token.get("access_token")
    if not access:
        raise FileNotFoundError("Missing credentials/tiktok_token.json; run: py auth_social.py tiktok")
    if token_expired(token):
        token = _refresh_token(config, token)
    return str(token["access_token"])


def authorize(config: AppConfig, *, port: int = 8765) -> dict[str, Any]:
    app = _app(config)
    scopes = config.tiktok.scopes or ["user.info.basic", "video.upload", "video.publish"]
    verifier, challenge = tiktok_pkce_pair()
    redirect = redirect_uri(port)
    state = secrets.token_urlsafe(16)
    params = {
        "client_key": app["client_key"],
        "scope": ",".join(scopes),
        "response_type": "code",
        "redirect_uri": redirect,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    open_authorize_url(f"{AUTH_URL}?{urlencode(params)}")
    code = wait_for_oauth_code(port, expected_state=state)
    resp = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": app["client_key"],
            "client_secret": app["client_secret"],
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect,
            "code_verifier": verifier,
        },
        timeout=60,
    )
    payload = resp.json()
    if not resp.ok or "error" in payload:
        desc = payload.get("error_description") or payload.get("error") or resp.text
        log_id = payload.get("log_id", "")
        raise RuntimeError(f"TikTok token exchange failed {resp.status_code}: {desc} {log_id}".strip())
    if "access_token" not in payload:
        raise RuntimeError(f"TikTok token exchange missing access_token: {resp.text}")
    token = {
        "access_token": payload["access_token"],
        "refresh_token": payload.get("refresh_token"),
        "open_id": payload.get("open_id"),
        "scope": payload.get("scope", ""),
    }
    if "expires_in" in payload:
        token = with_expiry(token, payload["expires_in"])
    save_json(_token_path(config), token)
    return token


def _creator_info(access_token: str, config: AppConfig) -> dict[str, Any]:
    return _post_publish_api(
        CREATOR_INFO_URL,
        access_token,
        {},
        config,
        operation="creator_info",
    )


def _upload_chunks(upload_url: str, video_path: Path, *, chunk_size: int, total_chunks: int) -> None:
    video_size = video_path.stat().st_size
    with video_path.open("rb") as fh:
        start = 0
        for index in range(total_chunks):
            if index == total_chunks - 1:
                chunk = fh.read()
            else:
                chunk = fh.read(chunk_size)
            if not chunk:
                raise RuntimeError("TikTok chunk upload read empty segment")
            end = start + len(chunk) - 1
            resp = requests.put(
                upload_url,
                data=chunk,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Range": f"bytes {start}-{end}/{video_size}",
                },
                timeout=600,
            )
            if not resp.ok:
                raise RuntimeError(f"TikTok chunk upload failed {resp.status_code}: {resp.text}")
            start = end + 1


def _poll_status(access_token: str, publish_id: str, *, timeout: float = 600.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    last: dict[str, Any] = {"publish_id": publish_id}
    while time.time() < deadline:
        resp = requests.post(
            STATUS_URL,
            headers=_headers(access_token),
            json={"publish_id": publish_id},
            timeout=60,
        )
        if not resp.ok:
            raise RuntimeError(f"TikTok status failed {resp.status_code}: {resp.text}")
        last = resp.json().get("data", {})
        status = str(last.get("status", "")).upper()
        if status in {"PUBLISH_COMPLETE", "SEND_TO_USER_INBOX", "FAILED"}:
            if status == "FAILED":
                raise RuntimeError(f"TikTok publish failed: {last}")
            return last
        time.sleep(3)
    raise TimeoutError(f"TikTok publish timed out: {last}")


def _init_upload(
    access_token: str,
    video_path: Path,
    caption: str,
    config: AppConfig,
) -> dict[str, Any]:
    tiktok = config.tiktok
    video_path = Path(video_path)
    video_size = video_path.stat().st_size
    chunk_size, total_chunks = _chunk_plan(video_size)
    source_info = {
        "source": "FILE_UPLOAD",
        "video_size": video_size,
        "chunk_size": chunk_size,
        "total_chunk_count": total_chunks,
    }
    inbox_mode = tiktok.post_mode == "inbox"
    if inbox_mode:
        body: dict[str, Any] = {"source_info": source_info}
        init_url = INBOX_INIT_URL
    else:
        body = {
            "post_info": {
                "title": caption[:2200],
                "privacy_level": tiktok.privacy_level,
                "disable_duet": tiktok.disable_duet,
                "disable_comment": tiktok.disable_comment,
                "disable_stitch": tiktok.disable_stitch,
                "video_cover_timestamp_ms": tiktok.cover_timestamp_ms,
            },
            "source_info": source_info,
        }
        init_url = DIRECT_INIT_URL

    data = _post_publish_api(init_url, access_token, body, config, operation="init_upload")
    upload_url = data.get("upload_url")
    publish_id = data.get("publish_id")
    if not upload_url or not publish_id:
        raise RuntimeError(f"TikTok init missing upload_url/publish_id: {data}")
    _upload_chunks(upload_url, video_path, chunk_size=chunk_size, total_chunks=total_chunks)
    return {"publish_id": publish_id, "inbox_mode": inbox_mode}


def post_video(
    video_path: Path,
    caption: str,
    config: AppConfig,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    tiktok = config.tiktok
    summary: dict[str, Any] = {
        "platform": "tiktok",
        "caption": caption,
        "post_mode": tiktok.post_mode,
        "dry_run": dry_run,
    }
    if dry_run:
        summary["status"] = "dry_run"
        return summary

    access = get_access_token(config)
    summary["creator"] = _creator_info(access, config)
    init = _init_upload(access, Path(video_path), caption, config)
    if init["inbox_mode"]:
        summary["status"] = "inbox"
        summary["note"] = "Video sent to TikTok inbox — open TikTok app to add caption and publish."
        summary["publish_id"] = init["publish_id"]
        return summary

    status = _poll_status(access, str(init["publish_id"]))
    summary["status"] = "posted"
    summary["publish"] = status
    return summary
