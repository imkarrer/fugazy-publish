"""Tests for server.py web UI: profile selection and YAML overrides."""
import io

import pytest
from fastapi.testclient import TestClient

import server

CONFIG_YAML = (server.PROJECT_ROOT / "config.yaml").read_text(encoding="utf-8")
CONFIG_CVSCC_YAML = (server.PROJECT_ROOT / "config.cvscc.yaml").read_text(encoding="utf-8")


@pytest.fixture
def project_root(tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text(CONFIG_YAML, encoding="utf-8")
    (tmp_path / "config.cvscc.yaml").write_text(CONFIG_CVSCC_YAML, encoding="utf-8")
    monkeypatch.setattr(server, "PROJECT_ROOT", tmp_path)
    return tmp_path


@pytest.fixture
def client(project_root):
    return TestClient(server.app)


def test_index_lists_both_profiles(client):
    html = client.get("/").text
    assert '<option value="default">default</option>' in html
    assert '<option value="cvscc">cvscc</option>' in html


def test_publish_with_profile_loads_that_config(client, monkeypatch):
    captured = {}

    def fake_publish(video_path, title, config=None, dry_run=False):
        captured["config"] = config
        return {"title": title}

    monkeypatch.setattr(server, "publish", fake_publish)

    response = client.post(
        "/publish",
        data={"title": "My clip", "profile": "cvscc"},
        files={"video": ("clip.mp4", io.BytesIO(b"fake video"), "video/mp4")},
    )

    assert response.status_code == 200
    assert captured["config"].paths.output_dir == "output/cvscc"


def test_publish_forbidden_override_is_400(client, monkeypatch):
    monkeypatch.setattr(server, "publish", lambda *a, **k: {})

    response = client.post(
        "/publish",
        data={"title": "My clip", "overrides": "paths:\n  output_dir: hacked\n"},
        files={"video": ("clip.mp4", io.BytesIO(b"fake video"), "video/mp4")},
    )

    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"]


def test_publish_unknown_profile_is_400(client, monkeypatch):
    monkeypatch.setattr(server, "publish", lambda *a, **k: {})

    response = client.post(
        "/publish",
        data={"title": "My clip", "profile": "nonexistent"},
        files={"video": ("clip.mp4", io.BytesIO(b"fake video"), "video/mp4")},
    )

    assert response.status_code == 400


def test_promote_with_profile_loads_that_config(client, monkeypatch):
    captured = {}

    def fake_promote_existing(youtube_url, title=None, config=None, dry_run=False, force_download=False):
        captured["config"] = config
        return {"youtube_url": youtube_url}

    monkeypatch.setattr(server, "promote_existing", fake_promote_existing)

    response = client.post(
        "/promote",
        data={"youtube_url": "https://youtu.be/xxxx", "profile": "cvscc"},
    )

    assert response.status_code == 200
    assert captured["config"].paths.output_dir == "output/cvscc"


def test_promote_forbidden_override_is_400(client, monkeypatch):
    monkeypatch.setattr(server, "promote_existing", lambda *a, **k: {})

    response = client.post(
        "/promote",
        data={
            "youtube_url": "https://youtu.be/xxxx",
            "overrides": "paths:\n  output_dir: hacked\n",
        },
    )

    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"]
