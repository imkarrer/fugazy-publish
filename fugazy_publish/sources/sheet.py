"""Google Sheet + Drive folder source: the club's input channel."""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from fugazy_publish.config import AppConfig, credentials_dir
from fugazy_publish.sources import Source, Submission
from fugazy_publish.sources.sheet_rows import row_to_submission_parts

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

RESERVED_HEADERS = {"file", "title", "submitter", "publish", "status", "links", "error"}


def _token_path(config: AppConfig) -> Path:
    return credentials_dir(config) / "google_inbox_token.json"


def _client_secret_path(config: AppConfig) -> Path:
    return credentials_dir(config) / "client_secret.json"


def get_credentials(config: AppConfig, *, port: int = 8765) -> Credentials:
    """Google OAuth for the Sheets/Drive inbox, kept in its own token file
    so re-authorizing the inbox never touches YouTube's token."""
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
            "Download the club's Google client_secret.json from Google Cloud Console."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), SCOPES)
    creds = flow.run_local_server(port=port)
    token_file.write_text(creds.to_json(), encoding="utf-8")
    return creds


def authorize(config: AppConfig, *, port: int = 8765) -> dict[str, Any]:
    """CLI entry point for auth_social.py's 'inbox' target.

    Returns only what is safe to print: the token file keeps the secrets
    (token, refresh_token, client_secret), never stdout.
    """
    creds = get_credentials(config, port=port)
    return {
        "scopes": list(creds.scopes or []),
        "expiry": str(creds.expiry) if creds.expiry else None,
        "token_file": str(_token_path(config)),
    }


def build_services(config: AppConfig, *, port: int = 8765) -> tuple[Any, Any]:
    creds = get_credentials(config, port=port)
    sheets = build("sheets", "v4", credentials=creds)
    drive = build("drive", "v3", credentials=creds)
    return sheets, drive


def create_source(config: AppConfig) -> "SheetSource":
    sheets, drive = build_services(config)
    return SheetSource(sheets, drive, config.inbox.sheet_id, config.inbox.sheet_name)


_DRIVE_ID_PATTERNS = (
    re.compile(r"/d/([a-zA-Z0-9_-]+)"),
    re.compile(r"[?&]id=([a-zA-Z0-9_-]+)"),
)


def _extract_drive_file_id(ref: str) -> str:
    for pattern in _DRIVE_ID_PATTERNS:
        match = pattern.search(ref)
        if match:
            return match.group(1)
    return ref.strip()


def _column_letter(index: int) -> str:
    index += 1
    letters = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in ("true", "yes", "1")


def _extract_links(result: dict[str, Any]) -> str:
    links = []
    youtube = result.get("youtube") or {}
    youtube_url = youtube.get("url") or result.get("youtube_url")
    if youtube_url:
        links.append(f"YouTube: {youtube_url}")

    social_results = (result.get("social") or {}).get("results") or {}

    tiktok = social_results.get("tiktok") or result.get("tiktok") or {}
    tiktok_url = tiktok.get("url") if isinstance(tiktok, dict) else None
    if tiktok_url:
        links.append(f"TikTok: {tiktok_url}")

    instagram = social_results.get("instagram") or result.get("instagram") or {}
    instagram_url = instagram.get("url") if isinstance(instagram, dict) else None
    if instagram_url:
        links.append(f"Instagram: {instagram_url}")

    return "\n".join(links)


class SheetSource(Source):
    """Source that reads submissions from a Google Sheet; files come from Drive."""

    def __init__(self, sheets_service: Any, drive_service: Any, sheet_id: str, sheet_name: str = "Sheet1"):
        self.sheets = sheets_service
        self.drive = drive_service
        self.sheet_id = sheet_id
        self.sheet_name = sheet_name

    def _read_sheet(self) -> tuple[list[str], list[list[str]]]:
        resp = (
            self.sheets.spreadsheets()
            .values()
            .get(spreadsheetId=self.sheet_id, range=self.sheet_name)
            .execute()
        )
        values = resp.get("values", [])
        headers = values[0] if values else []
        rows = values[1:]
        return headers, rows

    def _write_cell(self, row_number: int, col_index: int, value: str) -> None:
        a1 = f"{self.sheet_name}!{_column_letter(col_index)}{row_number}"
        self.sheets.spreadsheets().values().update(
            spreadsheetId=self.sheet_id,
            range=a1,
            valueInputOption="RAW",
            body={"values": [[value]]},
        ).execute()

    def _col(self, headers: list[str], name: str) -> int | None:
        for i, header in enumerate(headers):
            if header.lower() == name:
                return i
        return None

    def _to_submission(self, headers: list[str], row: list[str], row_number: int) -> Submission:
        fields, overrides, _errors = row_to_submission_parts(headers, row)
        return Submission(
            id=str(row_number),
            video=None,
            ref=fields.get("file", ""),
            overrides=overrides,
            submitter=fields.get("submitter", ""),
        )

    def pending(self) -> list[Submission]:
        headers, rows = self._read_sheet()
        submissions = []
        for offset, row in enumerate(rows):
            row = list(row) + [""] * (len(headers) - len(row))
            fields, _overrides, _errors = row_to_submission_parts(headers, row)
            if not _is_truthy(fields.get("publish", "")):
                continue
            if fields.get("status", "").strip():
                continue
            submissions.append(self._to_submission(headers, row, offset + 2))
        return submissions

    def stuck(self) -> list[Submission]:
        headers, rows = self._read_sheet()
        submissions = []
        for offset, row in enumerate(rows):
            row = list(row) + [""] * (len(headers) - len(row))
            fields, _overrides, _errors = row_to_submission_parts(headers, row)
            if fields.get("status", "").strip().lower() == "processing":
                submissions.append(self._to_submission(headers, row, offset + 2))
        return submissions

    def claim(self, submission: Submission) -> bool:
        headers, rows = self._read_sheet()
        row_number = int(submission.id)
        row = rows[row_number - 2] if 0 <= row_number - 2 < len(rows) else []
        row = list(row) + [""] * (len(headers) - len(row))

        _fields, _overrides, errors = row_to_submission_parts(headers, row)
        if errors:
            self._fail_row(headers, row_number, "; ".join(errors))
            return False

        status_col = self._col(headers, "status")
        if status_col is None:
            raise ValueError(f'Sheet "{self.sheet_name}" has no "status" column')
        self._write_cell(row_number, status_col, "processing")

        confirm_headers, confirm_rows = self._read_sheet()
        confirm_row = confirm_rows[row_number - 2] if 0 <= row_number - 2 < len(confirm_rows) else []
        confirm_status = confirm_row[status_col] if status_col < len(confirm_row) else ""
        return confirm_status.strip().lower() == "processing"

    def fetch(self, submission: Submission, dest_dir: Path) -> Path:
        file_id = _extract_drive_file_id(submission.ref)
        meta = self.drive.files().get(fileId=file_id, fields="name").execute()
        name = meta.get("name") or f"{submission.id}.mp4"

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / name

        request = self.drive.files().get_media(fileId=file_id)
        with io.FileIO(dest_path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _status, done = downloader.next_chunk()
        return dest_path

    def report_published(self, submission: Submission, result: dict) -> None:
        headers, _rows = self._read_sheet()
        row_number = int(submission.id)
        status_col = self._col(headers, "status")
        if status_col is not None:
            self._write_cell(row_number, status_col, "published")
        links_col = self._col(headers, "links")
        if links_col is not None:
            self._write_cell(row_number, links_col, _extract_links(result))

    def report_failed(self, submission: Submission, error: str) -> None:
        headers, _rows = self._read_sheet()
        self._fail_row(headers, int(submission.id), error)

    def _fail_row(self, headers: list[str], row_number: int, error: str) -> None:
        status_col = self._col(headers, "status")
        if status_col is not None:
            self._write_cell(row_number, status_col, "failed")
        error_col = self._col(headers, "error")
        if error_col is not None:
            self._write_cell(row_number, error_col, error)
