"""Tests for the Google Sheet source."""
from __future__ import annotations

from fugazy_publish.sources import sheet
from fugazy_publish.sources.sheet import SheetSource

HEADERS = ["file", "title", "publish", "status", "links", "error"]


class FakeValues:
    def __init__(self, sheet_data: dict[str, list[list[str]]]):
        self._data = sheet_data
        self._pending_range = None
        self._pending_body = None

    def get(self, spreadsheetId, range):  # noqa: A002
        return FakeExecute({"values": [list(row) for row in self._data[range]]})

    def update(self, spreadsheetId, range, valueInputOption, body):  # noqa: A002
        self._pending_range = range
        self._pending_body = body
        return FakeExecute({})

    def _apply_update(self, sheet_name):
        if self._pending_range is None:
            return
        # range looks like "Sheet1!B3"
        _, cell = self._pending_range.split("!")
        col_letters = "".join(c for c in cell if c.isalpha())
        row_number = int("".join(c for c in cell if c.isdigit()))
        col_index = 0
        for ch in col_letters:
            col_index = col_index * 26 + (ord(ch) - ord("A") + 1)
        col_index -= 1

        rows = self._data[sheet_name]
        row = rows[row_number - 1]
        while len(row) <= col_index:
            row.append("")
        row[col_index] = self._pending_body["values"][0][0]
        self._pending_range = None
        self._pending_body = None


class FakeExecute:
    def __init__(self, result):
        self._result = result

    def execute(self):
        return self._result


class FakeSpreadsheets:
    def __init__(self, values: FakeValues):
        self._values = values

    def values(self):
        return self._values


class FakeSheetsService:
    def __init__(self, sheet_name: str, rows: list[list[str]]):
        self.sheet_name = sheet_name
        self.values = FakeValues({sheet_name: [HEADERS] + rows})

    def spreadsheets(self):
        return FakeSpreadsheets(self.values)

    def write(self, sheet_name, range_, body):
        self.values.update("sheet-id", range_, "RAW", body)
        self.values._apply_update(sheet_name)


def make_source(rows: list[list[str]]) -> tuple[SheetSource, FakeSheetsService]:
    service = FakeSheetsService("Sheet1", rows)
    # Wrap update() so it also mutates the backing rows, like a real sheet would.
    real_update = service.values.update

    def update_and_apply(spreadsheetId, range, valueInputOption, body):  # noqa: A002
        result = real_update(spreadsheetId, range, valueInputOption, body)
        service.values._apply_update("Sheet1")
        return result

    service.values.update = update_and_apply
    source = SheetSource(service, drive_service=None, sheet_id="sheet-id", sheet_name="Sheet1")
    return source, service


def test_pending_picks_only_ticked_rows_with_no_status():
    source, _service = make_source(
        [
            ["abc123", "Run 1", "TRUE", "", "", ""],
            ["def456", "Run 2", "FALSE", "", "", ""],
            ["ghi789", "Run 3", "TRUE", "published", "", ""],
        ]
    )
    pending = source.pending()
    assert [s.id for s in pending] == ["2"]
    assert pending[0].ref == "abc123"


def test_claim_writes_processing():
    source, service = make_source([["abc123", "Run 1", "TRUE", "", "", ""]])
    submission = source.pending()[0]

    assert source.claim(submission) is True
    assert service.values._data["Sheet1"][1][3] == "processing"


def test_report_published_writes_links():
    source, service = make_source([["abc123", "Run 1", "TRUE", "processing", "", ""]])
    headers, rows = source._read_sheet()
    submission = source._to_submission(headers, rows[0], 2)

    result = {
        "youtube": {"url": "https://youtube.com/watch?v=abc"},
        "social": {"results": {"tiktok": {"url": "https://tiktok.com/x"}}},
    }
    source.report_published(submission, result)

    row = service.values._data["Sheet1"][1]
    assert row[3] == "published"
    assert "YouTube: https://youtube.com/watch?v=abc" in row[4]
    assert "TikTok: https://tiktok.com/x" in row[4]


def test_unknown_column_fails_at_claim():
    service = FakeSheetsService(
        "Sheet1", [["abc123", "Run 1", "TRUE", "", "", "", "weird value"]]
    )
    headers_with_typo = HEADERS + ["titel"]
    service.values._data["Sheet1"][0] = headers_with_typo
    real_update = service.values.update

    def update_and_apply(spreadsheetId, range, valueInputOption, body):  # noqa: A002
        result = real_update(spreadsheetId, range, valueInputOption, body)
        service.values._apply_update("Sheet1")
        return result

    service.values.update = update_and_apply
    source = SheetSource(service, drive_service=None, sheet_id="sheet-id", sheet_name="Sheet1")

    submission = source.pending()[0]
    assert source.claim(submission) is False

    row = service.values._data["Sheet1"][1]
    assert row[3] == "failed"
    assert 'Unknown column "titel"' in row[5]


def test_token_file_is_google_inbox_token_json():
    from fugazy_publish.config import AppConfig, PathsConfig

    config = AppConfig(paths=PathsConfig(credentials_dir="credentials"))
    assert sheet._token_path(config).name == "google_inbox_token.json"


def test_authorize_never_returns_secrets(monkeypatch, tmp_path):
    """auth_social.py prints what authorize() returns, so it must hold no secret."""
    from types import SimpleNamespace

    from fugazy_publish.sources import sheet

    fake = SimpleNamespace(
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
        expiry=None,
        token="ya29.live-access-token",
        refresh_token="1//refresh",
        client_secret="club-oauth-secret",
        to_json=lambda: '{"token": "ya29.live-access-token", "client_secret": "club-oauth-secret"}',
    )
    monkeypatch.setattr(sheet, "get_credentials", lambda config, port=8765: fake)
    monkeypatch.setattr(sheet, "_token_path", lambda config: tmp_path / "google_inbox_token.json")
    out = sheet.authorize(object())
    assert not {"token", "refresh_token", "client_secret", "access_token", "id_token"} & set(out)
    assert "ya29" not in repr(out) and "club-oauth-secret" not in repr(out)
