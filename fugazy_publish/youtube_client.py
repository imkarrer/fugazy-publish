"""YouTube Data API v3 resumable upload with OAuth."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from fugazy_publish.config import AppConfig, apply_sponsor, credentials_dir, format_hashtags

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def build_description(config: AppConfig) -> str:
    """Build the YouTube description, substituting {bio_link}/{tags} and
    appending hashtags when the template has no {tags} placeholder, then
    adding the sponsor line."""
    return apply_sponsor(_description_body(config), config.sponsor_line)


def _description_body(config: AppConfig) -> str:
    text = (config.youtube.default_description or "").replace(
        "{bio_link}", config.bio_link
    )
    hashtags = format_hashtags(config.youtube.default_tags or config.tags)
    if "{tags}" in text:
        return text.replace("{tags}", hashtags)
    if hashtags:
        return f"{text.rstrip()}\n\n{hashtags}" if text.strip() else hashtags
    return text


def _token_path(config: AppConfig) -> Path:
    return credentials_dir(config) / "token.json"


def _client_secret_path(config: AppConfig) -> Path:
    cred_dir = credentials_dir(config)
    for name in ("client_secret.json", "credentials.json"):
        p = cred_dir / name
        if p.is_file():
            return p
    return cred_dir / "client_secret.json"


def get_credentials(config: AppConfig) -> Credentials:
    cred_dir = credentials_dir(config)
    cred_dir.mkdir(parents=True, exist_ok=True)
    token_file = _token_path(config)
    client_secret = _client_secret_path(config)

    creds: Credentials | None = None
    if token_file.is_file():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_file.write_text(creds.to_json(), encoding="utf-8")
        return creds

    if not client_secret.is_file():
        raise FileNotFoundError(
            f"Missing OAuth client secret at {client_secret}. "
            "Download from Google Cloud Console (YouTube Data API v3)."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), SCOPES)
    creds = flow.run_local_server(port=0)
    token_file.write_text(creds.to_json(), encoding="utf-8")
    return creds


def upload_video(
    video_path: Path,
    title: str,
    config: AppConfig,
    description: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Upload video via resumable upload; returns API response snippet."""
    video_path = Path(video_path)
    if not video_path.is_file():
        raise FileNotFoundError(video_path)

    creds = get_credentials(config)
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title,
            "description": description if description is not None else build_description(config),
            "tags": tags if tags is not None else config.youtube.default_tags,
            "categoryId": config.youtube.category_id,
        },
        "status": {
            "privacyStatus": config.youtube.privacy_status,
            # Explicitly declare audience: made-for-kids disables comments (COPPA).
            "selfDeclaredMadeForKids": config.youtube.made_for_kids,
        },
    }

    media = MediaFileUpload(
        str(video_path),
        chunksize=1024 * 1024,
        resumable=True,
        mimetype="video/*",
    )

    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    try:
        while response is None:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                print(f"YouTube upload progress: {pct}%")
    except HttpError as exc:
        raise RuntimeError(f"YouTube upload failed: {exc}") from exc

    return response
