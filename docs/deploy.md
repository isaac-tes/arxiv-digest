# Share settings across devices (digest server)

The iOS app has three connection modes (Settings → Connection):

| Mode | Where config + removed papers live | Synced? | Needs a server? |
|---|---|---|---|
| **On this device** (default) | on the phone | no | no |
| **Server** | on the digest server | **yes**: every device pointing at the same server shares them | yes |
| **Demo** | in memory (sample papers) | no | no |

To share keywords, authors, feeds, weights and removed papers between devices
(iPhone, iPad, a Mac), run the **digest server** (`server/`, a FastAPI app around
the same `arxiv_digest.py` engine as the CLI and GUI) somewhere all of them can
reach, and switch each device to **Server**.

!!! tip "No server? Copy one file instead"
    In **On this device** mode nothing is synced, but you can move the config by
    hand as a single JSON file, both ways (see [Copy the config file](#copy-the-config-file-without-a-server)).

---

## 1. Requirements

- Python 3.12+ and [uv](https://docs.astral.sh/uv/) (installs into your home
  directory, no root needed):
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- The **whole repository**, not just `server/`: the server imports the engine
  (`arxiv_digest.py`) from the repo root.
  ```bash
  git clone https://github.com/isaac-tes/arxiv-digest.git
  cd arxiv-digest
  git switch feat/swift_ios   # until the iOS work is merged into main
  ```

## 2. Start the server

```bash
cd server
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Check it from the same machine:

```bash
curl http://127.0.0.1:8000/health      # {"status":"ok","mode":"local"}
```

- Without an access token the server **only answers this machine** (it checks
  the caller and the `Host` header). Other devices need a token, see step 4.
- The first past-week load fetches from arXiv (~20–40 s); later loads come from
  the server's 1 h cache.
- Stop it with `Ctrl-C`. Your config and removed papers are kept in
  `server/digest.db` (SQLite), so restarting doesn't lose them.

## 3. Optional: start from your GUI settings

Point the server at a saved GUI profile; it is used as the config for a user who
has none stored yet:

```bash
DIGEST_DEFAULT_CONFIG_PATH=~/.arxiv_scraper/profiles/<name>.json \
  uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

This seeds the server once. Edits made later in the app are stored on the
server and don't change the profile file.

## 4. Make it reachable from your devices

First create an **access token** (a shared secret every device sends) and start
the server with it. Keep it private, like a password:

```bash
export DIGEST_ACCESS_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
echo "$DIGEST_ACCESS_TOKEN"     # copy this into each device (step 5)
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

With a token set, every request except `/health` must send it
(`Authorization: Bearer <token>`); without it the server answers `401`. Then
pick how devices reach the server:

| Setup | Server command | URL to enter on each device |
|---|---|---|
| **Same Wi-Fi at home** (Mac or Linux box) | `--host 0.0.0.0` | `http://<server-LAN-IP>:8000` |
| **From anywhere, private**: [Tailscale](https://tailscale.com) on the server and every device | `--host 0.0.0.0` | `http://<server-tailscale-IP>:8000` |
| **Remote Linux machine, Mac only**: SSH tunnel | `--host 127.0.0.1` | on the Mac: `ssh -N -L 8000:127.0.0.1:8000 you@host`, then `http://127.0.0.1:8000` |

Find the LAN IP with `ipconfig getifaddr en0` (Mac) or `hostname -I` (Linux).
If a device can't connect, open `http://<url>/health` in its browser first;
firewalls and guest/eduroam networks that isolate devices are the usual cause.

!!! warning "One shared user, plain HTTP"
    `local` mode has a single shared user and no accounts; the access token is
    the only lock, and plain `http://` doesn't encrypt it. Use it on networks you
    trust (home Wi-Fi, Tailscale, an SSH tunnel), never directly on the public
    internet. See [Going public](#going-public-remote-mode).

What the server guards against:

- **Other devices without the token**: `401` (or `403` when no token is configured).
- **Web pages you visit**: no CORS headers by default, and the localhost-only
  check rejects foreign `Host` names, so a page can't read or change your
  config through `http://127.0.0.1:8000` (including DNS rebinding).
- **Fetching arbitrary URLs**: feed URLs must be on `arxiv.org`; a config with
  other hosts, or more than 50 feeds, is rejected (`422`).
- **Remote mode with the default JWT secret**: the server refuses to start.

## 5. Connect each device

**iPhone / iPad**: Settings → Connection → **Server** → enter the URL from
step 4 and the **access token** → **Connect**. The status line reads
*Connected · local mode*; a wrong token shows *Missing or wrong access token*.
The token is stored in the iOS Keychain. Allow **Local Network** access when iOS
asks (needed for LAN addresses).

**Web GUI (`arxiv-gui`, two-way)**: sidebar → **🔄 Sync with server** → enter
the URL and the access token → **Connect**. The first time it asks once whose
config both sides should use: **Use server's** or **Upload mine**. After that:

- every GUI session starts from the server's config and removed papers;
  **⬇ Download** refreshes them;
- **⬆ Save to server**, saving a profile, and *Write project config* upload the
  config; removing or restoring a paper goes to the server straight away;
- if the server can't be reached the GUI keeps working from its local copy
  (`arxiv_config.json`, which the `arxiv-digest` CLI also reads) and shows
  *Offline*; save again once the server is back.

The address and token are stored in `~/.arxiv_scraper/sync.json` (readable only
by you); `ARXIV_DIGEST_SERVER` / `ARXIV_DIGEST_TOKEN` override them. **Stop
syncing** goes back to local-only.

Named profiles stay on your computer: loading one and saving it sends it to the
server as the shared config.

**Mac app (optional)**: on Apple-silicon Macs the iOS app also runs as a Mac
app. In Xcode, open `ios/ArxivDigest.xcodeproj`, choose the destination **My Mac
(Designed for iPad)**, run it, and connect it to the same URL. (Not yet tested
on this project; report problems.)

Now a keyword added on the phone, a removal on the Mac, or a preset loaded on
either is saved to the server and shows on the other device after its next load
(pull to refresh).

## 6. Keep it running

=== "Linux with sudo (systemd)"

    A template unit is in `deploy/arxiv-digest.service`. Fill in `<youruser>`
    and the checkout path, then:

    ```bash
    sudo cp deploy/arxiv-digest.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now arxiv-digest
    systemctl status arxiv-digest
    ```

    Without root but with user lingering enabled (`loginctl enable-linger $USER`,
    which some distributions allow without sudo), copy the unit to
    `~/.config/systemd/user/`, remove its `User=` line, and use
    `systemctl --user enable --now arxiv-digest`.

=== "Linux without root (tmux)"

    Check first that long-running processes are allowed on the machine.

    ```bash
    tmux new -s digest
    cd ~/arxiv-digest/server && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
    # detach: Ctrl-b then d · reattach: tmux attach -t digest
    ```

    tmux sessions don't survive a reboot; start it again afterwards.

=== "Mac (while logged in)"

    Run the step 2 command in a Terminal window, or in a
    `tmux`/`screen` session. The Mac must be awake for other devices to sync.

**Updating**:
```bash
cd ~/arxiv-digest && git pull
cd server && uv sync
# then restart: Ctrl-C and rerun, or `sudo systemctl restart arxiv-digest`
```

## 7. Back up

Everything is in `server/digest.db`. Copy it while the server is stopped, e.g.
`cp server/digest.db ~/digest-backup-$(date +%F).db`.

## Copy the config file (without a server)

For **On this device** mode, or to move settings once: the config is a single
JSON file with the same format everywhere.

**Mac → iPhone**

1. GUI → **Profiles** tab → **Export** next to a saved profile (save the current
   config as a profile first if needed). This downloads `<name>.json`.
2. AirDrop the file to the iPhone and choose **arXiv Digest**, or save it to
   Files and use the app's Settings → **Config file** → **Import config…**.
3. The app opens **Config** with the imported settings; tap **Save**.

**iPhone → Mac**

1. App → Settings → **Config file** → **Export config** → AirDrop to the Mac
   (it arrives in Downloads as `arxiv-digest-config.json`).
2. GUI → **Profiles** tab → **Import profile from JSON** → pick the file.
3. Save it as a profile, or **Write project config** (and, if you sync,
   **⬆ Save to server**).

An import replaces the whole config (keywords, authors, feeds, weights, colors)
and isn't kept until you save. Removed papers aren't part of the file.

---

## Reference

### Server settings (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `DIGEST_MODE` | `local` | `local`: no auth, SQLite. `remote`: JWT login, multi-user |
| `DIGEST_DATABASE_URL` | `sqlite:///./digest.db` | Database (Postgres for `remote`) |
| `DIGEST_DEFAULT_CONFIG_PATH` | – | GUI profile used for users without a stored config |
| `DIGEST_JWT_SECRET` | `dev-secret-change-me` | **Change** in `remote` mode |
| `DIGEST_ACCESS_TOKEN` | – | Local mode: token every device must send; unset = this machine only |
| `DIGEST_CORS_ORIGINS` | `[]` (none) | Browser origins allowed to call the API; leave empty unless a web front end needs it |
| `ZOTERO_API_KEY`, `ZOTERO_LIBRARY_ID` | – | Enable *Save to Zotero* from the app via the Zotero Web API |

Without the Zotero variables the app offers **Share to Zotero** (the iOS share
sheet hands the paper to the Zotero app), and everything else works.

### Going public (`remote` mode)

```bash
export DIGEST_MODE=remote
export DIGEST_JWT_SECRET="$(openssl rand -hex 32)"
export DIGEST_DATABASE_URL="postgresql+psycopg://user:pass@host/db"
export DIGEST_CORS_ORIGINS='["https://yourapp.example"]'
```

Users register with `POST /auth/register` and log in with `POST /auth/token`.
The iOS app has no login screen yet, so `remote` mode isn't usable from the
app today. Put HTTPS in front (e.g. Caddy) before exposing it, and expect arXiv
to rate-limit a busy shared server; the server caches fetches for an hour.
