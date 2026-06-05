# Agon

**strength through loss**

Agon is a self-hosted relative density (RD) strength tracker built for people actively losing weight — whether through cut/bulk cycles, GLP-1 medications, or body recomposition. Unlike conventional strength trackers that measure absolute load, Agon measures how strong you are *relative to your current bodyweight*, making it the right tool when the scale is intentionally moving down.

---

## What is Relative Density?

```
RD = total session volume / (total session time × bodyweight)
```

A rising RD means you are getting stronger per pound of bodyweight — the signal that matters most during a cut, recomp, or weight-loss phase. A flat or rising RD alongside falling bodyweight means muscle is being preserved. That's the whole point.

---

## Features

- **Workout logging** — sets, reps, load, per-set timing, bodyweight
- **RD calculation** — automatic, per session and weekly trend; recalculated server-side
- **Training phases** — bulk, cut, recomp, deload, weight loss; chart shading and phase-aware macros
- **Trend chart** — weekly RD and bodyweight on a dual-axis chart with phase band overlays
- **Recomp score card** — at-a-glance read on whether you're building strength while losing weight
- **Macro calculator** — BMR, TDEE, and daily macro targets based on profile and current phase
- **AI Insights** — plain-English questions answered using your actual training data (Gemini and Claude API)
- **Meal plan builder** — sends your current macro targets to AI Insights for a personalized plan
- **Progress anatomy** — interactive body figure showing muscle group training frequency
- **Exercise bank** — shared library with muscle tagging, multipliers, formula hints; admin exercises are protected
- **Protocols / supplements** — log peptides, medications, and supplements; passed to AI as context
- **Import / export** — scoped XLSX export with date and phase filters; full data import
- **External API** — per-user read-only API key for connecting external AI tools (header-authenticated)
- **Multi-user** — admin, guest, and demo roles with per-user data isolation
- **Public registration** — optional, with admin approval queue
- **Two-factor authentication** — TOTP-based 2FA, any authenticator app
- **PWA** — installable on Android and iOS, runs full-screen, supports rotation

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, SQLite |
| Frontend | Vanilla HTML / JS / CSS (single file) |
| Infrastructure | Docker, nginx, OMV |
| CI/CD | GitHub Actions to GHCR |
| AI | Gemini API, Claude API |

---

## Deployment

Agon is designed for self-hosted deployment via Docker. Each user runs their own instance.

### Quick start

```bash
curl -O https://raw.githubusercontent.com/shredness/rd-tracker/master/docker-compose.yml
# Edit environment variables (see below) — set a strong SECRET_KEY
docker-compose up -d
```

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | *(insecure default)* | JWT signing key — **must be changed**; app refuses to start with the default |
| `ADMIN_USER` | `manny` | Admin account username |
| `ADMIN_PASS` | *(insecure default)* | Admin account password — **change this** |
| `DB_PATH` | `/data/sessions.db` | SQLite database path |
| `ALLOWED_ORIGINS` | `https://agon.savo.us,http://localhost,http://localhost:3800` | Comma-separated CORS origins |
| `ALLOW_REGISTRATION` | `false` | Set `true` to enable public sign-up (guest role, pending approval) |
| `ALLOW_DEFAULT_SECRET` | `false` | Local-dev escape hatch to run with the default `SECRET_KEY`. **Never set in production.** |

> **Important:** The app will refuse to start if `SECRET_KEY` is still the known default value, unless `ALLOW_DEFAULT_SECRET=true`. Always set a strong, unique `SECRET_KEY` and `ADMIN_PASS` in production.

---

## Security Model

- **Passwords** — hashed with bcrypt; never stored or returned in plaintext
- **Password complexity** — minimum 10 characters with uppercase, lowercase, number, and special character, enforced on every password-setting path
- **JWT auth** — all protected endpoints gated by token validation; admin endpoints require admin role
- **Two-factor (TOTP)** — optional per user; secret encrypted at rest with Fernet
- **Data isolation** — every data query is scoped to the authenticated user's ID
- **Demo account** — read-only, enforced server-side on every mutation
- **Rate limiting** — login, registration, and external-data endpoints are throttled per IP at the nginx layer
- **External API key** — passed via `Authorization: Bearer` header, not URL parameters
- **AI keys** — encrypted at rest with Fernet derived from `SECRET_KEY`
- **Parameterized queries** — throughout; no string-built SQL

---

## Password Requirements

All passwords (admin-created, self-registered, or changed) must have:

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

Any user can enable TOTP-based 2FA from **Settings to Two-factor authentication**:

1. Click **Enable two-factor authentication**
2. Scan the QR code with Google Authenticator, Authy, or any TOTP app
3. Enter the 6-digit confirmation code

Once enabled, every login requires password plus authenticator code. Admins can disable 2FA for any user via the Admin panel (for recovery if a device is lost).

---

## External API

Each user can generate a read-only API key from **Settings to External API**. The key authenticates a single read-only endpoint that returns the user's full training data as JSON.

```bash
curl -H "Authorization: Bearer agon_YOUR_KEY" https://your-server/api/external/data
```

`X-API-Key: agon_YOUR_KEY` is also accepted. The legacy `?key=` query parameter still works but is deprecated — it leaks the key into server logs and browser history. Revoke a key at any time from the same panel.

---

## Accessing the App

After deployment, visit `http://your-server:3800` (or your configured domain/reverse proxy URL).

The app is a PWA — on Android, Chrome will prompt to install it. On iOS, use Safari, Share, Add to Home Screen. It runs full-screen and supports both orientations.

---

## Development

```bash
git clone https://github.com/shredness/rd-tracker.git
cd rd-tracker

# Backend
cd backend
pip install -r requirements.txt
ALLOW_DEFAULT_SECRET=true uvicorn main:app --reload

# Frontend — open frontend/index.html directly, or serve via any static server
```

### Versioning

- Patch bump (`0.x.y`) — fixes and small tweaks
- Minor bump (`0.x.0`) — new user-facing feature or security release
- Tracked in the `APP_VERSION` constant in `frontend/index.html`
- Changelog maintained in the `CHANGELOG` JS object, surfaced via the What's New modal

### CI/CD

Pushes to `master` trigger GitHub Actions workflows that build and push Docker images to GHCR:

- `ghcr.io/shredness/rd-tracker-backend:latest`
- `ghcr.io/shredness/rd-tracker-frontend:latest`

---

## Current Version

**v0.6.0**

See the in-app What's New modal for the full changelog.

---

## License

Personal use. Not licensed for redistribution.
