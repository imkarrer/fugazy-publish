"""Load YAML configuration into typed dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"

# Per-video overrides are allowed for these YAML key paths.
# These are the leaf keys that _from_dict reads, minus forbidden sections.
PER_VIDEO_KEYS = frozenset({
    # Top-level keys that are allowed
    "title",
    "bio_link",
    "sponsor_line",
    "tags",
    
    # Teaser keys
    "teaser.start_seconds",
    "teaser.duration_seconds",
    
    # Teaser overlay keys (excluding the mapping itself)
    "teaser.overlay.enabled",
    "teaser.overlay.text",
    "teaser.overlay.link",
    "teaser.overlay.font",
    "teaser.overlay.font_size",
    "teaser.overlay.font_color",
    "teaser.overlay.position",
    "teaser.overlay.x",
    "teaser.overlay.y",
    "teaser.overlay.show_seconds",
    "teaser.overlay.font_file",
    
    # Teaser audio keys (excluding the mapping itself)
    "teaser.audio.enabled",
    "teaser.audio.clean_youtube",
    "teaser.audio.highpass_hz",
    "teaser.audio.lowpass_hz",
    "teaser.audio.noise_reduction_db",
    "teaser.audio.noise_floor_db",
    "teaser.audio.track_noise",
    "teaser.audio.boost_quiet",
    "teaser.audio.compress_threshold_db",
    "teaser.audio.compress_ratio",
    "teaser.audio.normalize",
    "teaser.audio.target_loudness",
    
    # Teaser audio notch keys (excluding the mapping itself)
    "teaser.audio.notch.enabled",
    "teaser.audio.notch.freq_hz",
    "teaser.audio.notch.width_hz",
    "teaser.audio.notch.gain_db",
    
    # Audio keys (excluding the mapping itself)
    "audio.enabled",
    "audio.clean_youtube",
    "audio.highpass_hz",
    "audio.lowpass_hz",
    "audio.noise_reduction_db",
    "audio.noise_floor_db",
    "audio.track_noise",
    "audio.boost_quiet",
    "audio.compress_threshold_db",
    "audio.compress_ratio",
    "audio.normalize",
    "audio.target_loudness",
    
    # Audio notch keys (excluding the mapping itself)
    "audio.notch.enabled",
    "audio.notch.freq_hz",
    "audio.notch.width_hz",
    "audio.notch.gain_db",
    
    # YouTube keys (including both current and legacy spellings)
    "youtube.category_id",
    "youtube.privacy_status",
    "youtube.privacy",
    "youtube.default_description",
    "youtube.default_tags",
    "youtube.made_for_kids",
    
    # Captions keys
    "captions.tiktok",
    "captions.instagram",
    
    # Social keys
    "social.platforms",
    "social.first_comment",
    
    # TikTok keys
    "tiktok.post_mode",
    "tiktok.privacy_level",
    "tiktok.disable_duet",
    "tiktok.disable_comment",
    "tiktok.disable_stitch",
    "tiktok.cover_timestamp_ms",
    "tiktok.scopes",
    
    # Instagram keys
    "instagram.media_type",
    "instagram.share_to_feed",
    "instagram.ig_user_id",
    "instagram.caption",
    "instagram.first_comment",
})

FORBIDDEN_SECTIONS = frozenset({'paths', 'retries', 'upload_post'})


def merge_overrides(base: dict, override: dict) -> dict:
    """Deep merge two dictionaries, with override taking precedence.
    
    Mappings merge key by key, lists and scalars replace.
    Neither input is mutated.
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            # Recursively merge nested dictionaries
            result[key] = merge_overrides(result[key], value)
        else:
            # Replace scalar or list values
            result[key] = value
    return result


def override_errors(override: dict) -> list[str]:
    """Validate override dict and return list of error messages.
    
    Each error message is a string describing one invalid key path.
    """
    errors = []
    
    def _flatten_dict(d, parent_key=""):
        """Flatten a nested dict into dotted key paths."""
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}.{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(_flatten_dict(v, new_key))
            else:
                items.append(new_key)
        return items
    
    flattened = _flatten_dict(override)
    
    for key in flattened:
        # Check for forbidden sections
        first_part = key.split('.')[0]
        if first_part in FORBIDDEN_SECTIONS:
            errors.append(f"{key}: not allowed per video")
            continue
            
        # Check for unknown keys
        if key not in PER_VIDEO_KEYS:
            errors.append(f"{key}: unknown setting")
    
    return errors


def title_from(overrides) -> str | None:
    """Extract title from overrides dict if present."""
    if not overrides:
        return None
    return overrides.get('title')


@dataclass
class OverlayConfig:
    enabled: bool = True
    text: str = "Full run on YouTube — link in bio"
    link: str = "youtube.com/@FugazyMiata"
    font: str = "arial"
    font_size: int = 28
    font_color: str = "white"
    position: str = "bottom"
    x: str = "(w-text_w)/2"
    y: str = "h-60"
    show_seconds: float = 3.0
    # Empty means auto-detect; see teaser.resolve_font_file.
    font_file: str = ""


@dataclass
class NotchConfig:
    """Parametric cut for a fixed-frequency whine (e.g. the GoPro's own wind DSP).

    Implemented as an ffmpeg ``equalizer`` band so it surgically dips one narrow
    region instead of chopping the whole top end like a low-pass would. Defaults
    target the ~3.7 kHz whine measured on the current GoPro; retune ``freq_hz``
    if you change cameras, or set ``enabled: false`` to drop it entirely.
    """

    enabled: bool = True
    freq_hz: float = 3700.0     # center of the whine to cut
    width_hz: float = 700.0     # how wide a band around it to attenuate
    gain_db: float = -14.0      # cut depth (negative = attenuate)


@dataclass
class AudioConfig:
    """Wind-noise cleanup applied to the teaser audio track.

    Onboard mics get hammered by low-frequency wind roar that buries exhaust
    and passenger chatter. The defaults roll off sub-bass rumble, run an
    adaptive FFT denoiser to knock down the broadband wind hiss, then lift the
    quieter stuff back up so it stays audible.
    """

    enabled: bool = True
    clean_youtube: bool = True      # also clean the full-length YouTube upload
    highpass_hz: int = 120          # roll off sub-bass wind rumble; 0 disables
    lowpass_hz: int = 0             # optional top-end roll off; 0 disables
    noise_reduction_db: float = 12.0    # afftdn nr (0.01-97), higher = more aggressive
    noise_floor_db: float = -25.0       # afftdn nf (-80 to -20)
    track_noise: bool = True            # afftdn adaptive noise tracking (tn)
    boost_quiet: bool = True            # compress to lift exhaust/voices
    compress_threshold_db: float = -24.0
    compress_ratio: float = 3.0
    normalize: bool = True              # final loudnorm pass for consistent level
    target_loudness: float = -16.0      # loudnorm integrated LUFS (I)
    notch: NotchConfig = field(default_factory=NotchConfig)


@dataclass
class TeaserConfig:
    start_seconds: float = 0.0
    duration_seconds: float = 15.0
    overlay: OverlayConfig = field(default_factory=OverlayConfig)


@dataclass
class YouTubeConfig:
    category_id: str = "2"
    privacy_status: str = "public"
    default_description: str = ""
    default_tags: list[str] = field(default_factory=list)
    made_for_kids: bool = False  # True disables comments (COPPA); keep False


@dataclass
class PlatformCaptions:
    title: str = ""
    first_comment: str = ""


@dataclass
class SocialConfig:
    platforms: list[str] = field(default_factory=lambda: ["tiktok", "instagram"])
    first_comment: str = ""
    tiktok: PlatformCaptions = field(default_factory=PlatformCaptions)


@dataclass
class TikTokConfig:
    post_mode: str = "inbox"  # inbox | direct
    privacy_level: str = "PUBLIC_TO_EVERYONE"
    disable_duet: bool = False
    disable_comment: bool = False
    disable_stitch: bool = False
    cover_timestamp_ms: int = 1000
    scopes: list[str] = field(default_factory=lambda: ["user.info.basic", "video.upload", "video.publish"])


@dataclass
class RetryConfig:
    max_attempts: int = 8
    initial_seconds: float = 10.0
    max_seconds: float = 600.0
    min_api_interval_seconds: float = 10.0


@dataclass
class InstagramConfig:
    media_type: str = "REELS"
    share_to_feed: bool = True
    ig_user_id: str = ""
    caption: str = ""
    first_comment: str = ""


@dataclass
class PathsConfig:
    output_dir: str = "output"
    credentials_dir: str = "credentials"


DEFAULT_SPONSOR_LINE = "Built with Flox: https://flox.dev"


def apply_sponsor(text: str, line: str) -> str:
    """Put the sponsor line at {sponsor}, or append it once if there is none."""
    if "{sponsor}" in text:
        return text.replace("{sponsor}", line)
    if not line or line in text:
        return text
    return f"{text.rstrip()}\n\n{line}" if text.strip() else line


@dataclass
class AppConfig:
    bio_link: str = ""
    # Credited on every YouTube description and social caption; "" turns it off.
    sponsor_line: str = DEFAULT_SPONSOR_LINE
    tags: list[str] = field(default_factory=list)
    paths: PathsConfig = field(default_factory=PathsConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    teaser: TeaserConfig = field(default_factory=TeaserConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    youtube: YouTubeConfig = field(default_factory=YouTubeConfig)
    social: SocialConfig = field(default_factory=SocialConfig)
    tiktok: TikTokConfig = field(default_factory=TikTokConfig)
    instagram: InstagramConfig = field(default_factory=InstagramConfig)


def _overlay_from_dict(data: dict[str, Any] | None) -> OverlayConfig:
    data = data or {}
    pos = str(data.get("position", "bottom"))
    if pos == "bottom_center":
        pos = "bottom"
    if pos == "top_center":
        pos = "top"
    return OverlayConfig(
        enabled=bool(data.get("enabled", True)),
        text=str(data.get("text", OverlayConfig.text)),
        link=str(data.get("link", OverlayConfig.link)),
        font=str(data.get("font", "arial")),
        font_size=int(data.get("font_size", OverlayConfig.font_size)),
        font_color=str(data.get("font_color", OverlayConfig.font_color)),
        position=pos,
        x=str(data.get("x", "(w-text_w)/2")),
        y=str(data.get("y", "h-60")),
        show_seconds=float(data.get("show_seconds", OverlayConfig.show_seconds)),
        font_file=str(data.get("font_file", OverlayConfig.font_file)),
    )


def _notch_from_dict(data: dict[str, Any] | None) -> NotchConfig:
    data = data or {}
    return NotchConfig(
        enabled=bool(data.get("enabled", True)),
        freq_hz=float(data.get("freq_hz", NotchConfig.freq_hz)),
        width_hz=float(data.get("width_hz", NotchConfig.width_hz)),
        gain_db=float(data.get("gain_db", NotchConfig.gain_db)),
    )


def _audio_from_dict(data: dict[str, Any] | None) -> AudioConfig:
    data = data or {}
    return AudioConfig(
        enabled=bool(data.get("enabled", True)),
        clean_youtube=bool(data.get("clean_youtube", AudioConfig.clean_youtube)),
        highpass_hz=int(data.get("highpass_hz", AudioConfig.highpass_hz)),
        lowpass_hz=int(data.get("lowpass_hz", AudioConfig.lowpass_hz)),
        noise_reduction_db=float(
            data.get("noise_reduction_db", AudioConfig.noise_reduction_db)
        ),
        noise_floor_db=float(data.get("noise_floor_db", AudioConfig.noise_floor_db)),
        track_noise=bool(data.get("track_noise", AudioConfig.track_noise)),
        boost_quiet=bool(data.get("boost_quiet", AudioConfig.boost_quiet)),
        compress_threshold_db=float(
            data.get("compress_threshold_db", AudioConfig.compress_threshold_db)
        ),
        compress_ratio=float(data.get("compress_ratio", AudioConfig.compress_ratio)),
        normalize=bool(data.get("normalize", AudioConfig.normalize)),
        target_loudness=float(data.get("target_loudness", AudioConfig.target_loudness)),
        notch=_notch_from_dict(data.get("notch")),
    )


def _normalize_tags(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, str):
        raw = raw.split()
    return [str(tag).strip().lstrip("#") for tag in raw if str(tag).strip()]


def format_hashtags(tags: list[str]) -> str:
    return " ".join(f"#{tag.lstrip('#')}" for tag in tags if tag)


def _resolve_tags(data: dict[str, Any]) -> list[str]:
    if data.get("tags") is not None:
        return _normalize_tags(data.get("tags"))
    youtube = data.get("youtube") or {}
    return _normalize_tags(youtube.get("default_tags"))


def _platform_captions(data: dict[str, Any] | None) -> PlatformCaptions:
    data = data or {}
    return PlatformCaptions(
        title=str(data.get("title", "")),
        first_comment=str(data.get("first_comment", "")),
    )


def _from_dict(data: dict[str, Any]) -> AppConfig:
    paths = data.get("paths") or {}
    retries = data.get("retries") or {}
    teaser = data.get("teaser") or {}
    youtube = data.get("youtube") or {}
    social = data.get("social") or {}
    upload_post = data.get("upload_post") or {}  # legacy
    instagram = data.get("instagram") or {}
    tiktok = data.get("tiktok") or {}
    captions = data.get("captions") or {}
    first_comments = upload_post.get("first_comments") or {}

    shared_first_comment = str(
        social.get("first_comment")
        or upload_post.get("first_comment")
        or ""
    )

    tiktok_caps = _platform_captions(social.get("tiktok") or upload_post.get("tiktok"))
    ig_caps = _platform_captions(social.get("instagram") or upload_post.get("instagram"))

    if captions.get("tiktok") and not tiktok_caps.title:
        tiktok_caps.title = str(captions["tiktok"])
    ig_caption = str(instagram.get("caption") or captions.get("instagram") or "")

    if shared_first_comment and not tiktok_caps.first_comment:
        tiktok_caps.first_comment = shared_first_comment
    if shared_first_comment and not ig_caps.first_comment:
        ig_caps.first_comment = shared_first_comment
    if first_comments.get("tiktok") and not tiktok_caps.first_comment:
        tiktok_caps.first_comment = str(first_comments["tiktok"])
    if first_comments.get("instagram") and not ig_caps.first_comment:
        ig_caps.first_comment = str(first_comments["instagram"])

    platforms = social.get("platforms") or upload_post.get("platforms") or [
        "tiktok",
        "instagram",
    ]

    privacy = youtube.get("privacy_status") or youtube.get("privacy") or "public"
    description = youtube.get("default_description") or youtube.get("description_template") or ""
    tags = _resolve_tags(data)

    return AppConfig(
        bio_link=str(data.get("bio_link", "")),
        sponsor_line=str(data.get("sponsor_line", DEFAULT_SPONSOR_LINE) or ""),
        tags=tags,
        paths=PathsConfig(
            output_dir=str(paths.get("output_dir", "output")),
            credentials_dir=str(paths.get("credentials_dir", "credentials")),
        ),
        retry=RetryConfig(
            max_attempts=int(retries.get("max_attempts", tiktok.get("retry_max_attempts", 8))),
            initial_seconds=float(retries.get("initial_seconds", tiktok.get("retry_initial_seconds", 10.0))),
            max_seconds=float(retries.get("max_seconds", tiktok.get("retry_max_seconds", 600.0))),
            min_api_interval_seconds=float(
                retries.get("min_api_interval_seconds", tiktok.get("min_api_interval_seconds", 10.0))
            ),
        ),
        teaser=TeaserConfig(
            start_seconds=float(teaser.get("start_seconds", 0.0)),
            duration_seconds=float(teaser.get("duration_seconds", 15.0)),
            overlay=_overlay_from_dict(teaser.get("overlay")),
        ),
        audio=_audio_from_dict(data.get("audio") or teaser.get("audio")),
        youtube=YouTubeConfig(
            category_id=str(youtube.get("category_id", "2")),
            privacy_status=str(privacy),
            default_description=str(description),
            default_tags=tags,
            made_for_kids=bool(youtube.get("made_for_kids", False)),
        ),
        social=SocialConfig(
            platforms=list(platforms),
            first_comment=shared_first_comment,
            tiktok=tiktok_caps,
        ),
        tiktok=TikTokConfig(
            post_mode=str(tiktok.get("post_mode", "inbox")),
            privacy_level=str(tiktok.get("privacy_level", "PUBLIC_TO_EVERYONE")),
            disable_duet=bool(tiktok.get("disable_duet", False)),
            disable_comment=bool(tiktok.get("disable_comment", False)),
            disable_stitch=bool(tiktok.get("disable_stitch", False)),
            cover_timestamp_ms=int(tiktok.get("cover_timestamp_ms", 1000)),
            scopes=list(
                tiktok.get("scopes") or ["user.info.basic", "video.upload", "video.publish"]
            ),
        ),
        instagram=InstagramConfig(
            media_type=str(instagram.get("media_type", "REELS")),
            share_to_feed=bool(instagram.get("share_to_feed", True)),
            ig_user_id=str(instagram.get("ig_user_id", "")),
            caption=ig_caption,
            first_comment=str(
                ig_caps.first_comment
                or shared_first_comment
                or first_comments.get("instagram", "")
            ),
        ),
    )


def load_config(config_path: Path | str | None = None, overrides=None) -> AppConfig:
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if not path.is_file():
        raise FileNotFoundError(
            f"Missing {path}. Copy config.example.yaml to config.yaml and edit it."
        )
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Config root must be a mapping: {path}")
    
    if overrides is not None:
        # Validate overrides
        errors = override_errors(overrides)
        if errors:
            raise ValueError("Invalid per-video override(s):\n" + "\n".join(errors))
        
        # Merge overrides
        raw = merge_overrides(raw, overrides)
    
    return _from_dict(raw)


def credentials_dir(config: AppConfig) -> Path:
    return PROJECT_ROOT / config.paths.credentials_dir


def output_dir(config: AppConfig) -> Path:
    d = PROJECT_ROOT / config.paths.output_dir
    d.mkdir(parents=True, exist_ok=True)
    return d
