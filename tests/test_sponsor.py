"""Every published video credits the sponsor exactly once."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from fugazy_publish.config import DEFAULT_SPONSOR_LINE, apply_sponsor, load_config
from fugazy_publish.social import fan_out
from fugazy_publish.youtube_client import build_description

ROOT = Path(__file__).resolve().parent.parent
LINE = "Built with Flox: https://flox.dev"


@pytest.fixture
def config():
    return load_config(ROOT / "config.example.yaml")


def test_appended_after_the_text():
    assert apply_sponsor("Run 3\n\n#miata", LINE) == f"Run 3\n\n#miata\n\n{LINE}"


def test_placeholder_puts_it_where_the_template_says():
    assert apply_sponsor("Run 3 · {sponsor} · #miata", LINE) == f"Run 3 · {LINE} · #miata"


def test_never_added_twice():
    once = apply_sponsor("Run 3", LINE)
    assert apply_sponsor(once, LINE) == once


def test_empty_line_turns_it_off():
    assert apply_sponsor("Run 3", "") == "Run 3"


def test_missing_from_config_uses_the_default(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("bio_link: https://example.com\n", encoding="utf-8")
    assert load_config(path).sponsor_line == DEFAULT_SPONSOR_LINE


def test_blank_in_config_turns_it_off(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text('sponsor_line: ""\n', encoding="utf-8")
    assert load_config(path).sponsor_line == ""


def test_youtube_description_ends_with_it(config):
    description = build_description(config)
    assert description.endswith(LINE)
    assert "#autocross" in description


def test_every_social_caption_carries_it(config, tmp_path):
    summary = fan_out(tmp_path / "teaser.mp4", config, "https://youtu.be/x", dry_run=True)
    for platform, caption in summary["captions"].items():
        assert caption.count(LINE) == 1, platform


def test_turned_off_leaves_captions_alone(config, tmp_path):
    summary = fan_out(tmp_path / "t.mp4", replace(config, sponsor_line=""), "https://youtu.be/x", dry_run=True)
    assert all("flox.dev" not in c for c in summary["captions"].values())
