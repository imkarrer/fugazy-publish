# fugazy-publish

One-button YouTube funnel publisher for @fugazymiata: upload full autocross run to YouTube, auto-trim a teaser, fan out to TikTok and Instagram.

## Requirements

- Google Cloud project with **YouTube Data API v3** enabled (new uploads only)
- Developer apps for **TikTok** and **Instagram** (native APIs — no Upload-Post)
- macOS, Linux or WSL2: [Flox](https://flox.dev/docs/install-flox/install), which supplies everything else
- Native Windows: Python 3.10+ (`py` launcher) and [ffmpeg](https://ffmpeg.org/) on PATH (`winget install FFmpeg`)

## Quick setup: macOS, Linux, WSL2

```bash
flox activate                      # Python 3.12, ffmpeg, an overlay font, Python packages
python publish.py run.mp4 --title "Run 3"
```

The first activation installs the Python packages and copies `config.example.yaml` to `config.yaml`. The web UI runs as a Flox service at http://127.0.0.1:8000:

```bash
flox activate --start-services
```

Run the tests with `flox activate -- pytest`. Then continue from step 1 below.

## Quick setup: native Windows

```powershell
cd C:\Users\isaac\fugazy-publish
py -m pip install -r requirements.txt
copy config.example.yaml config.yaml   # if needed
powershell -ExecutionPolicy Bypass -File setup.ps1
```

1. Edit `config.yaml` — tags, captions, teaser overlay, `bio_link`
2. Add OAuth app credentials to `credentials/` (see `credentials/README.txt`)
3. Authorize each platform once:

```powershell
py auth_social.py tiktok
py auth_social.py instagram
```

4. For **new** YouTube uploads: put Google OAuth JSON at `credentials/client_secret.json`

## YouTube integration setup

**Full step-by-step guide: [docs/youtube-setup.md](docs/youtube-setup.md)** — Google Cloud project, enabling YouTube Data API v3, OAuth consent + Desktop client, first-run authorization, and quota. (Needed only for new uploads; promoting existing videos needs no YouTube credentials, and no GitHub Pages is required.)

## Social platform setup

**Full step-by-step guide: [docs/social-setup.md](docs/social-setup.md)** — covers creating the TikTok and Meta developer accounts/apps, scopes, redirect URIs, and one-time OAuth authorization.

| Platform | Portal | Credentials | Auth command |
|----------|--------|-------------|--------------|
| **TikTok** | [developers.tiktok.com](https://developers.tiktok.com/) | `tiktok_app.json`, `tiktok_token.json` | `py auth_social.py tiktok` |
| **Instagram** | [developers.facebook.com](https://developers.facebook.com/) | `meta_app.json`, `meta_token.json` | `py auth_social.py instagram` |

TikTok OAuth callback uses `http://127.0.0.1:8765/callback`. Instagram (Meta) requires HTTPS — use `https://localhost:8765/callback` in Facebook Login settings; the auth command handles the local certificate.

**TikTok `post_mode`:**
- `inbox` (default) — video lands in TikTok app inbox; tap to publish. No audit required.
- `direct` — auto-posts to profile. Requires [TikTok Content Posting audit](https://developers.tiktok.com/doc/content-sharing-guidelines) for public visibility.

**Instagram** requires a Business or Creator account linked to a Facebook Page.

There are **no monthly upload limits** from a middleman — you post directly via each platform's API (subject to their own rate limits and any API billing).

## Config

Shared tags and caption placeholders:

```yaml
tags:
  - autocross
  - miata
  - fugazymiata

captions:
  tiktok: |
    New autocross run — full onboard.
    Full run on YouTube: {bio_link}
    {tags}

social:
  platforms: [tiktok, instagram]
  first_comment: "Full run on YouTube: {bio_link}"
```

Placeholders: `{youtube_url}`, `{bio_link}`, `{tags}` (hashtags from `tags` list). Same `tags` list is used for YouTube video metadata.

## Configurable teaser overlay

```yaml
teaser:
  start_seconds: 0
  duration_seconds: 15
  overlay:
    enabled: true
    text: "Full run on YouTube — link in bio"
    font_size: 28
    position: bottom_center
```

## Inbox Worker

**Full documentation: [docs/inbox.md](docs/inbox.md)** — explains how to set up and run the inbox worker for automated publishing from a folder or Google Sheet.

Run the inbox worker with `python inbox.py --config config.yaml --source folder --once`.

## Windows quick start

| Action | How |
|---|---|
| **Promote one existing YouTube video** | Double-click `Promote.bat`, paste URL |
| **Promote all channel videos** | Double-click `Promote-All.bat` (uses `channel-videos.txt`) |
| **Web UI** | Double-click `Start-Server.bat` → http://127.0.0.1:8000 |
| **New upload from local file** | Drag MP4 onto `Publish.bat` |

## Promote existing YouTube videos (backfill)

```powershell
py promote.py https://youtu.be/VIDEO_ID
py promote.py dQw4w9WgXcQ --dry-run
py promote.py --file channel-videos.txt
```

Downloads are cached at `output/downloads/{video_id}.mp4`.

## CLI (new uploads)

```powershell
py publish.py "C:\path\run.mp4" --title "SCCA ProSolo Run 3"
py publish.py run.mp4 --dry-run
```

## Publish flow

1. Upload full video to YouTube (OAuth)
2. FFmpeg trims teaser with overlay text
3. Native APIs post teaser to TikTok and Instagram

## License

[MIT](LICENSE) © Isaac Karrer
