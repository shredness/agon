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

- **Workout logging** — sets, reps, load, per-set timing, bodyweight; exercises reorderable within a session
- **RD calculation** — automatic, per session and weekly trend; recalculated server-side
- **Training phases** — bulk, cut, recomp, deload, weight loss; chart shading and phase-aware macros
- **Trend chart** — weekly RD and bodyweight on a dual-axis chart with phase band overlays
- **Recomp score card** — at-a-glance read on whether you're building strength while losing weight
- **Macro calculator** — BMR, TDEE, and daily macro targets based on profile and current phase
- **Block Rep Curve** — per-exercise fatigue decay visualization, total reps trend, Set 1 adaptation trend, load reset arc; for fixed-load accessory blocks
- **AI Insights** — plain-English questions answered using your actual training data (Gemini and Claude API); protocols with active/past/upcoming status passed as context
- **Meal plan builder** — sends your current macro targets to AI Insights for a personalized plan
- **Progress anatomy** — interactive body figure showing muscle group training frequency
- **Exercise bank** — shared library with muscle tagging, multipliers, formula hints; alphabetically sorted everywhere
- **Protocols / supplements** — log with start/end dates; AI receives active vs discontinued vs upcoming context
- **Import / export** — scoped XLSX export with date range presets and phase filters; full data import
- **External API** — per-user read-only API key, header-authenticated (`Authorization: Bearer`)
- **Multi-user** — admin, guest, and demo roles with per-user data isolation
- **Public registration** — optional, with admin approval queue; email address as username
- **Two-factor authentication** — TOTP-based 2FA, any authenticator app
- **PWA** — installable on Android and iOS, runs full-screen, supports rotation; auto-updates on deploy without reinstall

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, SQLite |
| Frontend | Vanilla HTML / JS / CSS (single file) |
| Infrastructure | Docker, nginx, OMV (kaiju) |
| CI/CD | GitHub Actions → GHCR |
| AI | Gemini API, Claude API |

---

## Deployment

Agon is designed for self-hosted deployment via Docker.

### Quick start

```bash
curl -O https://raw.githubusercontent.com/shredness/rd-tracker/master/docker-compose.yml
# Edit environment variables — set a strong SECRET_KEY
docker-compose up -d
```

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | *(insecure default)* | JWT signing key — **must be changed**; app refuses to start with the default |
| `ADMIN_USER` | `manny` | Admin account username |
| `ADMIN_PASS` | *(insecure default)* | Admin account password — **change this** |
| `DB_PATH` | `/data/sessions.db` | SQLite database path |
| `ALLOWED_ORIGINS` | `https://agon.savo.us,...` | Comma-separated CORS origins |
| `ALLOW_REGISTRATION` | `false` | Set `true` to enable public sign-up (pending admin approval) |
| `ALLOW_DEFAULT_SECRET` | `false` | Local-dev only — never set in production |

---

## Security Model

- Passwords hashed with bcrypt; complexity enforced (10+ chars, upper, lower, digit, special)
- JWT auth on all protected endpoints; admin role enforced server-side
- Token revocation: deleted users are rejected immediately on next request
- TOTP 2FA optional per user; secret encrypted at rest with Fernet
- Data isolation: every query scoped to the authenticated user's ID
- Rate limiting at nginx: login and register capped at 10 req/min per IP
- External API key via `Authorization: Bearer` header (not URL parameter)
- AI keys encrypted at rest; parameterized queries throughout

### Validating rate limiting

```bash
for i in {1..15}; do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST https://agon.savo.us/api/auth/login \
    -H "Content-Type: application/x-www-form-urlencoded" -d "username=test&password=test"
done
```

Expect `401` for the first ~15 requests, then `503` once the burst is exceeded.

---

## Password Requirements

- Minimum 10 characters
- At least one uppercase letter, one lowercase letter, one number, one special character

---

## The Method

Agon is built around two training approaches:

**Accessory blocks — escalating density, fixed time, cumulative reps**
Fixed load across multiple sets, AMRAP each set, fixed rest interval. The goal is to accumulate a target number of total reps (default 50, configurable per user and per exercise) before increasing the load. Load increments are small — 1 lb for smaller muscle groups, up to 1.5 lb for larger ones. Based on Schoenfeld's work on rep ranges and fatigue-based progressive overload.

**Compound lifts — dual wave, weekly +1**
10–12 sets across two ascending load waves, starting weight increasing +1 lb per week. Wave 2 exploits post-activation potentiation from Wave 1.

**Timed efforts**
Max reps in a fixed time window (e.g. 20 minutes pull-ups). No fixed set count.

The **Block Rep Curve** in the Progress tab shows set-by-set fatigue decay, cumulative reps trend vs threshold, Set 1 adaptation over time, and a load reset arc. See The Method tab in the in-app guide for full methodology and references.

---

## Registration & Approval

When `ALLOW_REGISTRATION=true`, new users register with an email address and land in `pending` status. The Admin panel shows a pending queue with Approve / Reject controls.

---

## External API

```bash
curl -H "Authorization: Bearer agon_YOUR_KEY" https://your-server/api/external/data
```

`X-API-Key: agon_YOUR_KEY` also accepted. The legacy `?key=` query param still works but is deprecated.

---

## Development

```bash
git clone https://github.com/shredness/rd-tracker.git
cd rd-tracker
cd backend && pip install -r requirements.txt
ALLOW_DEFAULT_SECRET=true uvicorn main:app --reload
```

CI/CD: pushes to `master` build and push Docker images to GHCR. The service worker cache version is injected automatically from `APP_VERSION` on each build, so PWA users get updates without reinstalling.

---

## Current Version

**v0.7.7**

See the in-app What's New modal for the full changelog.

---

## License

Personal use. Not licensed for redistribution.
