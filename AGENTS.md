# Agent instructions: fugazy-publish

A Python tool that publishes a video: full run to YouTube, a trimmed teaser to
TikTok and Instagram. It serves more than one channel (@fugazymiata, and the
Chippewa Valley Sports Car Club) through separate config files, and is growing
an inbox worker that publishes queued videos, each with its own partial config.

## The proof

```bash
flox activate -- pytest -ra         # what CI runs; every test passes
```

The Flox environment supplies Python, ffmpeg and the font, and its hook
installs `requirements.txt` and `requirements-dev.txt` into a venv. A new
dependency goes in one of those files, never in `.flox/`.

## Rules

1. **Tests never touch the network or a real account.** Fake the Google,
   TikTok, Meta and Discord clients (monkeypatch, or an object with the same
   methods). No test reads `credentials/` or a real `config.yaml`. Use
   `config.example.yaml`, or a config written into `tmp_path`.
2. **The default behaviour does not change.** `python publish.py run.mp4`
   with no new flags, and the web UI with no new choices made, work exactly
   as before. New behaviour is opt-in: a flag, a config key, a form field.
3. **Config is the contract.** Settings are YAML keys read by
   `_from_dict` in `fugazy_publish/config.py`. A new setting gets a dataclass
   field, a line in `_from_dict`, an entry in `config.example.yaml` with a
   comment, and, if it may be set per video, a place in the per-video key list.
   Never rename a YAML key that has shipped: `_from_dict` already reads some
   old spellings for compatibility.
4. **Per-video settings can't reach credentials.** An override (a sidecar
   YAML, a Sheet row, a web-form box) can never set `paths.*`, `retries.*` or
   `inbox.*`.
5. **Never publish twice.** Anything that publishes from a queue marks the
   item claimed before the first upload, and never retries a claimed item on
   its own. A crash leaves it for a person.
6. **Leave alone:** `.flox/`, `.github/`, `credentials/`, the `.bat` files and
   `.beads/`, unless the bead says otherwise.
