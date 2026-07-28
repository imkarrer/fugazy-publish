# YouTube integration setup

This guide covers everything needed to upload full runs to YouTube from
`fugazy-publish`. It uses the **YouTube Data API v3** with a Google **Desktop**
OAuth client and a localhost loopback redirect.

> **Do you even need this?** Only for **new uploads** (`publish.py`). Promoting
> videos that are *already* on your channel (`promote.py`) downloads the public
> video and does **not** require any YouTube credentials.

> **GitHub Pages?** Not required anywhere for YouTube. The OAuth redirect is a
> local loopback address, so there is no public URL to host. A hosted privacy
> policy page (which people often put on GitHub Pages) only matters if you later
> **publish** the OAuth app for people other than yourself — see
> [Going beyond yourself](#going-beyond-yourself-optional).

## What you'll end up with

| File | You create it | Contains |
|------|---------------|----------|
| `credentials/client_secret.json` | download from Google Cloud | OAuth Desktop client id/secret |
| `credentials/token.json` | created on first upload | your authorized access/refresh token |

`credentials/` is gitignored — these never leave your machine.

## Steps

### 1. Create a Google Cloud project

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Top bar → project picker → **New Project** (name it e.g. `fugazy-publish`).

### 2. Enable the YouTube Data API v3

1. **APIs & Services → Library**.
2. Search **YouTube Data API v3** → **Enable**.

### 3. Configure the OAuth consent screen

1. **APIs & Services → OAuth consent screen**.
2. User type: **External** → Create.
3. Fill the required app name and your support/developer email. You can leave the
   optional homepage/logo/policy fields blank while in testing.
4. **Scopes**: you can skip adding scopes here (the app requests
   `https://www.googleapis.com/auth/youtube.upload` at runtime).
5. **Test users**: add the Google account that owns the YouTube channel. While
   the app is in **Testing**, only listed test users can authorize — that's all
   you need for personal use.

### 4. Create the OAuth client credentials

1. **APIs & Services → Credentials → Create Credentials → OAuth client ID**.
2. Application type: **Desktop app** (important — this enables the localhost
   loopback redirect the tool uses; you do **not** register a redirect URI).
3. **Download JSON** and save it as:

   ```
   credentials/client_secret.json
   ```

   (`credentials/credentials.json` is also accepted.)

### 5. Authorize (first upload)

The first `publish.py` upload opens a browser to consent. If the app is in
Testing you'll see an **"unverified app"** warning — click **Advanced → Go to
… (unsafe)** to continue (expected for your own test app). On success the token
is saved to `credentials/token.json` and reused/refreshed automatically after.

```powershell
py publish.py "C:\path\run.mp4" --title "SCCA ProSolo Run 3"
```

To validate config without uploading:

```powershell
py publish.py "C:\path\run.mp4" --title "Test" --dry-run
```

## Upload quota

The YouTube Data API gives each project a default **10,000 units/day**, and a
video upload costs **~1,600 units** — roughly **6 uploads/day**. Request a quota
increase in the Cloud Console if you need more.

## Comments and audience

YouTube disables comments on videos flagged **made for kids**. This tool sets the
audience explicitly via `youtube.made_for_kids` in `config.yaml` (default
`false`, which keeps comments on). If comments are still off, also check your
channel-level default in **YouTube Studio → Settings → Channel → Advanced**.

## Going beyond yourself (optional)

Everything above works indefinitely for your **own** channel with the app in
Testing mode. You only need to **Publish** the OAuth app (Cloud Console → OAuth
consent screen → Publish app) if other people must authorize it. Publishing with
the sensitive `youtube.upload` scope triggers Google's OAuth verification, which
requires a homepage and a **privacy policy URL** — that policy page can be hosted
anywhere public, e.g. **GitHub Pages**. For a solo channel you can ignore this.

## Troubleshooting

- **`access_blocked` / app not verified** — add your account under **Test users**,
  or click through the Advanced → Continue warning.
- **`FileNotFoundError: client_secret.json`** — the OAuth JSON isn't at
  `credentials/client_secret.json`.
- **`quotaExceeded`** — you hit the daily unit cap; wait for reset or request more.
- **Wrong channel** — you authorized with a Google account that isn't the channel
  owner. Delete `credentials/token.json` and re-run to pick the right account.
