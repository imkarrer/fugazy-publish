"""Post Instagram Reels via the Meta Graph API."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

from fugazy_publish.config import AppConfig, credentials_dir
from fugazy_publish.http_retry import request_with_retry
from fugazy_publish.oauth_util import (
    cred_path,
    load_json,
    open_authorize_url,
    redirect_uri,
    save_json,
    wait_for_oauth_code,
)

GRAPH = "https://graph.facebook.com/v21.0"
SCOPES = (
    "instagram_basic",
    "instagram_content_publish",
    "pages_show_list",
    "pages_read_engagement",
    "business_management",
)
PAGE_SCOPES = {
    "pages_show_list",
    "pages_read_engagement",
    "pages_manage_posts",
    "pages_read_user_content",
    "business_management",
}


def _meta_error_code(resp: requests.Response) -> str:
    try:
        payload = resp.json()
    except ValueError:
        return ""
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("code") or error.get("type") or error.get("message") or "")
    return ""


def _app(config: AppConfig) -> dict[str, str]:
    data = load_json(cred_path(config, "meta_app.json"))
    app_id = data.get("app_id") or data.get("client_id") or ""
    app_secret = data.get("app_secret") or data.get("client_secret") or ""
    if not app_id:
        raise FileNotFoundError(
            "Missing credentials/meta_app.json with app_id and app_secret. "
            "Create a Meta app and run: py auth_social.py instagram"
        )
    return {"app_id": str(app_id), "app_secret": str(app_secret), "config_id": str(data.get("config_id") or "")}


def _token_path(config: AppConfig) -> Path:
    return cred_path(config, "meta_token.json")


def _get(config: AppConfig, path: str, params: dict[str, Any], *, throttle: bool = True) -> dict[str, Any]:
    resp = request_with_retry(
        "GET",
        f"{GRAPH}/{path}",
        retry=config.retry,
        operation=f"GET {path}",
        platform="Instagram",
        scope="instagram_graph",
        throttle=throttle,
        params=params,
        error_code_fn=_meta_error_code,
    )
    if not resp.ok:
        raise RuntimeError(f"Meta API GET {path} failed {resp.status_code}: {resp.text}")
    return resp.json()


def _post(
    config: AppConfig,
    path: str,
    params: dict[str, Any] | None = None,
    *,
    data: Any = None,
    timeout: float = 300.0,
    throttle: bool = True,
) -> dict[str, Any]:
    resp = request_with_retry(
        "POST",
        f"{GRAPH}/{path}",
        retry=config.retry,
        operation=f"POST {path}",
        platform="Instagram",
        scope="instagram_graph",
        throttle=throttle,
        params=params or {},
        data=data,
        timeout=timeout,
        error_code_fn=_meta_error_code,
    )
    if not resp.ok:
        raise RuntimeError(f"Meta API POST {path} failed {resp.status_code}: {resp.text}")
    return resp.json()


def _exchange_long_lived(config: AppConfig, app: dict[str, str], short_token: str) -> str:
    payload = _get(
        config,
        "oauth/access_token",
        {
            "grant_type": "fb_exchange_token",
            "client_id": app["app_id"],
            "client_secret": app["app_secret"],
            "fb_exchange_token": short_token,
        },
    )
    return str(payload["access_token"])


def _debug_token(config: AppConfig, app: dict[str, str], user_token: str) -> dict[str, Any]:
    payload = _get(
        config,
        "debug_token",
        {
            "input_token": user_token,
            "access_token": f"{app['app_id']}|{app['app_secret']}",
        },
    )
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def _page_ids_from_debug_token(debug: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for entry in debug.get("granular_scopes", []):
        if not isinstance(entry, dict):
            continue
        scope = str(entry.get("scope") or "")
        if scope not in PAGE_SCOPES and not scope.startswith("pages_") and scope != "instagram_basic":
            continue
        for page_id in entry.get("target_ids") or []:
            pid = str(page_id)
            if pid and pid not in seen:
                seen.add(pid)
                ids.append(pid)
    return ids


def _fetch_page_row(config: AppConfig, page_id: str, user_token: str) -> dict[str, Any] | None:
    try:
        return _get(
            config,
            page_id,
            {
                "access_token": user_token,
                "fields": "name,access_token,instagram_business_account",
            },
        )
    except RuntimeError:
        return None


def _try_list_pages(config: AppConfig, path: str, user_token: str) -> list[dict[str, Any]]:
    try:
        payload = _get(
            config,
            path,
            {"access_token": user_token, "fields": "id,name,access_token,instagram_business_account"},
        )
    except RuntimeError:
        return []
    data = payload.get("data", [])
    return data if isinstance(data, list) else []


def _collect_pages(config: AppConfig, user_token: str, app: dict[str, str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_rows(batch: list[dict[str, Any]]) -> None:
        for row in batch:
            pid = str(row.get("id") or "")
            if pid and pid not in seen:
                seen.add(pid)
                rows.append(row)

    add_rows(_try_list_pages(config, "me/accounts", user_token))
    add_rows(_try_list_pages(config, "me/assigned_pages", user_token))

    debug = _debug_token(config, app, user_token)
    for page_id in _page_ids_from_debug_token(debug):
        page = _fetch_page_row(config, page_id, user_token)
        if page:
            add_rows([page])

    return rows


def _resolve_ig_account(
    config: AppConfig,
    user_token: str,
    app: dict[str, str],
    ig_user_id: str = "",
) -> dict[str, str]:
    if ig_user_id:
        return {"ig_user_id": ig_user_id, "page_access_token": user_token}

    page_rows = _collect_pages(config, user_token, app)
    for page in page_rows:
        ig = page.get("instagram_business_account") or {}
        ig_id = ig.get("id")
        page_token = page.get("access_token")
        if ig_id and page_token:
            return {
                "ig_user_id": str(ig_id),
                "page_access_token": str(page_token),
                "page_name": str(page.get("name", "")),
            }

    if not page_rows:
        raise RuntimeError(
            "No Facebook Pages found for this login.\n"
            "1) Create a Facebook Page at https://www.facebook.com/pages/create\n"
            "2) In Instagram: Professional account -> link to that Page (Accounts Center)\n"
            "3) In Meta app: Facebook Login for Business -> Configurations -> create one "
            "with Pages + Instagram permissions (include business_management)\n"
            "4) Re-run: py auth_social.py instagram and select your Page when prompted"
        )

    names = ", ".join(str(p.get("name") or "Unnamed") for p in page_rows)
    raise RuntimeError(
        f"Found Facebook Page(s) ({names}) but none have Instagram linked. "
        "In Instagram: Settings -> Account type -> Professional (Business/Creator), "
        "then link to your Facebook Page via Accounts Center. "
        "Re-run: py auth_social.py instagram"
    )


def authorize(config: AppConfig, *, port: int = 8765) -> dict[str, Any]:
    app = _app(config)
    callback = redirect_uri(port, secure=True)
    config_id = str(app.get("config_id") or "").strip()
    params: dict[str, str] = {
        "client_id": app["app_id"],
        "redirect_uri": callback,
        "response_type": "code",
        "auth_type": "rerequest",
    }
    if config_id:
        params["config_id"] = config_id
    else:
        params["scope"] = ",".join(SCOPES)
    open_authorize_url(f"https://www.facebook.com/v21.0/dialog/oauth?{urlencode(params)}")
    code = wait_for_oauth_code(port, use_https=True, cert_dir=credentials_dir(config))
    short = _get(
        config,
        "oauth/access_token",
        {
            "client_id": app["app_id"],
            "client_secret": app["app_secret"],
            "redirect_uri": callback,
            "code": code,
        },
    )
    user_token = _exchange_long_lived(config, app, str(short["access_token"]))
    account = _resolve_ig_account(config, user_token, app, config.instagram.ig_user_id)
    token = {
        "user_access_token": user_token,
        **account,
    }
    save_json(_token_path(config), token)
    return token


def _session(config: AppConfig) -> dict[str, str]:
    token = load_json(_token_path(config))
    page_token = token.get("page_access_token") or token.get("user_access_token")
    ig_user_id = token.get("ig_user_id") or config.instagram.ig_user_id
    if not page_token or not ig_user_id:
        raise FileNotFoundError("Missing credentials/meta_token.json; run: py auth_social.py instagram")
    return {"access_token": str(page_token), "ig_user_id": str(ig_user_id)}


def _wait_container(config: AppConfig, creation_id: str, access_token: str, *, timeout: float = 600.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        payload = _get(
            config,
            creation_id,
            {"fields": "status_code", "access_token": access_token},
            throttle=False,
        )
        status = str(payload.get("status_code", "")).upper()
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError(f"Instagram container failed: {payload}")
        time.sleep(3)
    raise TimeoutError(f"Instagram container timed out: {creation_id}")


def _upload_resumable(config: AppConfig, video_path: Path, creation_id: str, access_token: str) -> None:
    video_path = Path(video_path)
    file_size = video_path.stat().st_size
    upload_url = f"https://rupload.facebook.com/ig-api-upload/v21.0/{creation_id}"
    with video_path.open("rb") as fh:
        resp = request_with_retry(
            "POST",
            upload_url,
            retry=config.retry,
            operation="resumable upload",
            platform="Instagram",
            scope="instagram_upload",
            headers={
                "Authorization": f"OAuth {access_token}",
                "offset": "0",
                "file_size": str(file_size),
            },
            data=fh.read(),
            timeout=600,
        )
    if not resp.ok:
        raise RuntimeError(f"Instagram upload failed {resp.status_code}: {resp.text}")


def _first_comment(config: AppConfig, media_id: str, message: str, access_token: str) -> dict[str, Any]:
    return _post(config, f"{media_id}/comments", {"message": message, "access_token": access_token})


def post_video(
    video_path: Path,
    caption: str,
    config: AppConfig,
    *,
    first_comment: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    ig_cfg = config.instagram
    summary: dict[str, Any] = {"platform": "instagram", "caption": caption, "dry_run": dry_run}
    if dry_run:
        summary["status"] = "dry_run"
        return summary

    session = _session(config)
    access = session["access_token"]
    ig_user_id = session["ig_user_id"]

    container = _post(
        config,
        f"{ig_user_id}/media",
        {
            "access_token": access,
            "media_type": ig_cfg.media_type,
            "upload_type": "resumable",
            "caption": caption,
            "share_to_feed": str(ig_cfg.share_to_feed).lower(),
        },
    )
    creation_id = str(container["id"])
    _upload_resumable(config, Path(video_path), creation_id, access)
    _wait_container(config, creation_id, access)
    published = _post(
        config,
        f"{ig_user_id}/media_publish",
        {"creation_id": creation_id, "access_token": access},
    )
    summary["publish"] = published
    media_id = published.get("id")
    if first_comment and media_id:
        summary["first_comment"] = _first_comment(config, str(media_id), first_comment, access)
    summary["status"] = "posted"
    return summary
