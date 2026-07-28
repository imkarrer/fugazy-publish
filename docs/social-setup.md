# Social platform setup (TikTok & Instagram)

This guide walks through creating the developer accounts, apps, and OAuth
credentials that `fugazy-publish` needs to post teasers to TikTok and Instagram.
It posts directly through each platform's native API — there is no third-party
middleman and no monthly upload cap (only each platform's own rate limits).

## What you'll end up with

All secrets live in the gitignored `credentials/` folder:

| File | Platform | You create it | Contains |
|------|----------|---------------|----------|
| `credentials/tiktok_app.json` | TikTok | manually | app `client_key`, `client_secret` |
| `credentials/tiktok_token.json` | TikTok | `auth_social.py` | access/refresh tokens |
| `credentials/meta_app.json` | Instagram | manually | app `app_id`, `app_secret`, optional `config_id` |
| `credentials/meta_token.json` | Instagram | `auth_social.py` | long-lived token, IG user id, page token |

The one-time authorization command for either platform is:

```powershell
py auth_social.py tiktok
py auth_social.py instagram
```

It opens your browser, captures the OAuth redirect on a local callback server
(`port 8765` by default; override with `--port`), exchanges the code for tokens,
and writes the `*_token.json` file. Tokens auto-refresh on later runs.

---

## TikTok

### 1. Create a developer account and app

1. Sign in at [developers.tiktok.com](https://developers.tiktok.com/) with the
   TikTok account you want to post from and complete developer registration.
2. **Manage apps → Connect an app** (create a new app).
3. Add these **products** to the app:
   - **Login Kit** (for OAuth)
   - **Content Posting API** (for uploading videos)

### 2. Configure scopes and redirect URI

1. Under the app's scopes, request:
   - `user.info.basic`
   - `video.upload`
   - `video.publish`
2. In **Login Kit → Desktop**, register the redirect URI exactly:

   ```
   http://127.0.0.1:8765/callback
   ```

   If the portal allows a wildcard, `http://127.0.0.1:*/callback/` also works and
   lets you change the `--port`. TikTok Desktop login uses PKCE, which the auth
   command handles automatically.

### 3. Save app credentials

Copy the app's **Client Key** and **Client Secret** into
`credentials/tiktok_app.json`:

```json
{
  "client_key": "YOUR_CLIENT_KEY",
  "client_secret": "YOUR_CLIENT_SECRET"
}
```

### 4. Authorize

```powershell
py auth_social.py tiktok
```

Approve the requested scopes in the browser. On success this writes
`credentials/tiktok_token.json`.

### 5. Choose a post mode

Set `tiktok.post_mode` in `config.yaml`:

- **`inbox`** (default) — the teaser is sent to your TikTok app inbox; you tap to
  add final caption and publish. **No app audit required.**
- **`direct`** — auto-posts to your profile. Requires passing the
  [TikTok Content Posting audit](https://developers.tiktok.com/doc/content-sharing-guidelines);
  until then an unaudited app can only post privately (self-only).

### TikTok troubleshooting

- **`redirect_uri` mismatch** — the URI in Login Kit must match byte-for-byte,
  including `http://` and the trailing `/callback` (and port).
- **`scope_not_authorized`** — the scope isn't enabled/approved on the app yet.
- **Too many pending inbox shares** — TikTok caps inbox mode at 5 unpublished
  shares per 24h; publish or clear them in the app.

---

## Instagram (Reels)

Instagram publishing goes through the **Meta Graph API**, so it needs a Meta app
plus a properly linked Instagram + Facebook Page.

### 1. Account prerequisites (do this first)

1. Your Instagram account must be **Business or Creator**
   (Instagram app → Settings → Account type).
2. Create a **Facebook Page** if you don't have one:
   [facebook.com/pages/create](https://www.facebook.com/pages/create).
3. **Link** the Instagram account to that Page via **Accounts Center**
   (Instagram → Settings → Accounts Center → add both accounts). Publishing fails
   without this link.

### 2. Create the Meta app

1. Go to [developers.facebook.com](https://developers.facebook.com/) → **My Apps
   → Create App**. Choose the **Business** app type.
2. Add these products:
   - **Facebook Login for Business**
   - **Instagram Graph API**

### 3. Permissions (scopes)

The auth flow requests these Graph permissions:

- `instagram_basic`
- `instagram_content_publish`
- `pages_show_list`
- `pages_read_engagement`
- `business_management`

You can supply them one of two ways:

- **Simple:** leave `config_id` out of `meta_app.json`; the auth command passes
  the scopes directly.
- **Recommended by Meta:** In **Facebook Login for Business → Configurations**,
  create a configuration that includes the permissions above, copy its
  **Configuration ID**, and put it in `meta_app.json` as `config_id`.

> While the app is in **Development** mode you can post to accounts whose users
> have a role on the app (Admin/Developer/Tester). Posting to **other** people's
> accounts requires Meta **App Review** for `instagram_content_publish`. For your
> own channel, add yourself as a tester and stay in development mode.

### 4. Configure the HTTPS redirect URI

Meta requires an **HTTPS** redirect. In **Facebook Login for Business →
Settings**, add the valid OAuth redirect URI:

```
https://localhost:8765/callback
```

The auth command starts a local HTTPS server using a self-signed certificate it
generates at `credentials/oauth-localhost.crt` / `.key`. When the browser warns
about the certificate on the callback, choose **Advanced → Continue to
localhost**.

### 5. Save app credentials

Copy the app's **App ID** and **App Secret** (Settings → Basic) into
`credentials/meta_app.json`:

```json
{
  "app_id": "YOUR_APP_ID",
  "app_secret": "YOUR_APP_SECRET",
  "config_id": "OPTIONAL_LOGIN_CONFIGURATION_ID"
}
```

### 6. Authorize

```powershell
py auth_social.py instagram
```

The command exchanges the code for a **long-lived** user token, then discovers
the Facebook Page and its linked Instagram Business account automatically, and
writes `credentials/meta_token.json`.

If you manage multiple IG accounts and want to pin one, set
`instagram.ig_user_id` in `config.yaml`.

### Instagram troubleshooting

- **"No Facebook Pages found"** — the login didn't grant Page access. Recheck the
  Accounts Center link (step 1) and that the login configuration includes the
  Pages + Instagram permissions (including `business_management`), then re-run.
- **"Page(s) found but none have Instagram linked"** — the IG account isn't a
  Professional account linked to that Page. Fix the link and re-run.
- **Certificate warning on callback** — expected (self-signed); choose Advanced →
  Continue to localhost.

---

## After authorizing

Verify everything is wired up with a dry run (no uploads, no posts):

```powershell
py publish.py "C:\path\run.mp4" --title "Test" --dry-run
```

Then do a real run and use `--review` to inspect the cleaned video and teaser
before it actually posts. See the main [README](../README.md) for the publish and
promote workflows.
