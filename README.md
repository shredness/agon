# Agon

**strength through loss**

Agon is a self-hosted relative density (RD) strength tracker built for people actively losing weight — whether through cut/bulk cycles, GLP-1 medications, or body recomposition. Unlike conventional strength trackers that measure absolute load, Agon measures how strong you are *relative to your current bodyweight*, making it the right tool when the scale is intentionally moving down.

---

## What is Relative Density?

```
RD = total session volume / (total session time × bodyweight)
```

A rising RD means you are getting stronger per pound of bodyweight — the signal that matters most during a cut, recomp, or weight loss phase. A flat or rising RD alongside falling bodyweight means muscle is being preserved. That's the whole point.

---

## Features

- **Workout logging** — sets, reps, load, per-set timing, bodyweight
- **RD calculation** — automatic, per session and weekly trend
- **Training phases** — bulk, cut, recomp, deload, weight loss; chart shading and phase-aware macros
- **Trend chart** — weekly RD and bodyweight on a dual-axis chart with phase band overlays
- **Recomp score card** — at-a-glance read on whether you're building strength while losing weight
- **Macro calculator** — BMR, TDEE, and daily macro targets based on profile and current phase
- **AI Insights** — plain-English questions answered using your actual training data (Gemini and Claude API)
- **Meal plan builder** — sends your current macro targets to AI Insights for a personalized meal plan
- **Progress anatomy** — interactive body figure showing muscle group training frequency
- **Exercise bank** — shared exercise library with muscle group tagging, multipliers, and formula hints
- **Protocols / supplements** — log peptides, medications, and supplements; passed to AI as context
- **Import / export** — scoped XLSX export with date and phase filters; full data import
- **External API** — per-user read-only API key for connecting external AI tools
- **Multi-user** — admin, guest, and demo roles with per-user data isolation
- **Public registration** — optional open registration with admin approval queue
- **Two-factor authentication** — TOTP-based 2FA, any authenticator app
- **PWA** — installable on Android and iOS, runs full-screen

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, SQLite |
| Frontend | Vanilla HTML / JS / CSS (single file) |
| Infrastructure | Docker, nginx, OMV |
| CI/CD | GitHub Actions → GHCR |
| AI | Gemini API, Claude API |

---

## Deployment

Agon is designed for self-hosted deployment via Docker. Each user runs their own instance.

### Quick start

```bash
# 1. Copy the compose file
curl -O https://raw.githubusercontent.com/shredness/rd-tracker/master/docker-compose.yml

# 2. Edit environment variables (see below)

# 3. Deploy
docker-compose up -d
```

### docker-compose.yml

```yaml
services:
  backend:
    container_name: agon-data
    image: ghcr.io/shredness/rd-tracker-backend:latest
    restart: unless-stopped
    volumes:
      - rdtracker:/data
    environment:
      - DB_PATH=/data/sessions.db
      - SECRET_KEY=change-this-to-a-long-random-string
      - ADMIN_USER=your_username
      - ADMIN_PASS=your_password
      # Set to "true" to enable public self-registration
      - ALLOW_REGISTRATION=false

  frontend:
    container_name: agon-ui
    image: ghcr.io/shredness/rd-tracker-frontend:latest
    restart: unless-stopped
    ports:
      - "3800:80"
    depends_on:
      - backend

volumes:
  rdtracker:
```

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | *(insecure default)* | JWT signing key — **change this** |
| `ADMIN_USER` | `manny` | Admin account username |
| `ADMIN_PASS` | *(insecure default)* | Admin account password — **change this** |
| `DB_PATH` | `/data/sessions.db` | SQLite database path |
| `ALLOW_REGISTRATION` | `false` | Set to `true` to enable public sign-up |

> **Important:** Always set a strong, unique `SECRET_KEY` and `ADMIN_PASS` in production. The defaults are intentionally weak and publicly known.

---

## Password Requirements

All passwords (admin-created or self-registered) must meet:

- Minimum 10 characters
- At least one uppercase letter
- At least one lowercase letter
- At least one number
- At least one special character

---

## Registration & Approval

When `ALLOW_REGISTRATION=true`:

1. A "Create an account" link appears on the login screen
2. New users register with an **email address** as their username
3. Their account is created with `status = pending` — they cannot log in yet
4. The admin sees a **Pending approval** queue at the top of the Admin panel
5. Admin approves (activates the account) or rejects (deletes it)

To close registrations, set `ALLOW_REGISTRATION=false` and redeploy. Existing accounts are unaffected.

---

## Two-Factor Authentication

Any user can enable TOTP-based 2FA from **Settings → Two-factor authentication**:

1. Click **Enable two-factor authentication**
2. Scan the QR code with Google Authenticator, Authy, or any TOTP app
3. Enter the 6-digit confirmation code

Once enabled, every login requires password + authenticator code. Admins can disable 2FA for any user via the Admin panel (for recovery if a device is lost).

---

## Accessing the App

After deployment, visit `http://your-server:3800` (or your configured domain/reverse proxy URL).

The app is a PWA — on Android, Chrome will prompt to install it. On iOS, use Safari → Share → Add to Home Screen.

---

## Development

```bash
git clone https://github.com/shredness/rd-tracker.git
cd rd-tracker

# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload

# Frontend — open frontend/index.html directly in a browser
# or serve via any static file server
```

### Versioning

- Patch bump (`0.x.y`) — any file change or bug fix
- Minor bump (`0.x.0`) — new user-facing feature
- Versions tracked in `APP_VERSION` constant in `frontend/index.html`
- Changelog maintained in the `CHANGELOG` JS object, surfaced via the What's New modal

### CI/CD

Pushes to `master` trigger GitHub Actions workflows that build and push Docker images to GHCR:

- `ghcr.io/shredness/rd-tracker-backend:latest`
- `ghcr.io/shredness/rd-tracker-frontend:latest`

---

## Current Version

**v0.5.1**

See the in-app What's New modal for full changelog.

---

## License

Personal use. Not licensed for redistribution.
