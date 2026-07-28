"""FastAPI web UI for publishing videos."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse

from fugazy_publish.config import load_config
from fugazy_publish.pipeline import promote_existing, publish

app = FastAPI(title="Fugazy Publish")

HTML_FORM = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Fugazy Publish</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; }
    label { display: block; margin-top: 1rem; font-weight: 600; }
    input[type=file], input[type=text] { width: 100%; margin-top: 0.25rem; box-sizing: border-box; }
    button { margin-top: 1.5rem; padding: 0.6rem 1.2rem; font-size: 1rem; cursor: pointer; }
    pre { background: #f4f4f4; padding: 1rem; overflow: auto; border-radius: 6px; }
    .err { color: #b00020; }
    section { margin-top: 2.5rem; padding-top: 1.5rem; border-top: 1px solid #ddd; }
    h2 { margin-bottom: 0.25rem; }
    p.hint { color: #555; margin-top: 0; }
  </style>
</head>
<body>
  <h1>Fugazy Publish</h1>

  <section>
    <h2>New upload</h2>
    <p class="hint">Upload a fresh clip to YouTube, then fan out a teaser.</p>
    <form action="/publish" method="post" enctype="multipart/form-data">
      <label for="video">Video file</label>
      <input id="video" name="video" type="file" accept="video/*" required />

      <label for="title">Title</label>
      <input id="title" name="title" type="text" required placeholder="Video title" />

      <label>
        <input type="checkbox" name="dry_run" value="true" /> Dry run (no uploads)
      </label>

      <button type="submit">Publish new video</button>
    </form>
  </section>

  <section>
    <h2>Promote existing YouTube</h2>
    <p class="hint">Download an existing video, cut a lead-in teaser, post to TikTok / IG linking back.</p>
    <form action="/promote" method="post">
      <label for="youtube_url">YouTube URL or video ID</label>
      <input id="youtube_url" name="youtube_url" type="text" required
        placeholder="https://youtu.be/xxxx or dQw4w9WgXcQ" />

      <label for="promo_title">Title override (optional)</label>
      <input id="promo_title" name="title" type="text" placeholder="Uses YouTube title if empty" />

      <label>
        <input type="checkbox" name="dry_run" value="true" /> Dry run
      </label>
      <label>
        <input type="checkbox" name="force_download" value="true" /> Force re-download
      </label>

      <button type="submit">Promote existing video</button>
    </form>
  </section>
</body>
</html>
"""


def _result_page(status: str, body: str) -> str:
    cls = "err" if status == "Error" else ""
    return f"""
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8" /><title>Result</title></head>
<body>
  <p><a href="/">Back</a></p>
  <h2 class="{cls}">{status}</h2>
  <pre>{body}</pre>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return HTML_FORM


@app.post("/publish", response_class=HTMLResponse)
async def publish_form(
    video: UploadFile = File(...),
    title: str = Form(...),
    dry_run: str | None = Form(None),
) -> str:
    is_dry = dry_run == "true"
    suffix = Path(video.filename or "upload.mp4").suffix or ".mp4"

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / f"upload{suffix}"
        content = await video.read()
        dest.write_bytes(content)

        cfg = load_config()
        try:
            result = publish(dest, title, config=cfg, dry_run=is_dry)
            body = json.dumps(result, indent=2, default=str)
            status = "OK"
        except Exception as exc:  # noqa: BLE001
            body = str(exc)
            status = "Error"

    return _result_page(status, body)


@app.post("/promote", response_class=HTMLResponse)
async def promote_form(
    youtube_url: str = Form(...),
    title: str = Form(""),
    dry_run: str | None = Form(None),
    force_download: str | None = Form(None),
) -> str:
    cfg = load_config()
    try:
        result = promote_existing(
            youtube_url,
            title=title or None,
            config=cfg,
            dry_run=dry_run == "true",
            force_download=force_download == "true",
        )
        body = json.dumps(result, indent=2, default=str)
        status = "OK"
    except Exception as exc:  # noqa: BLE001
        body = str(exc)
        status = "Error"

    return _result_page(status, body)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
