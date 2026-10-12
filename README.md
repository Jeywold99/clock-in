# CLOCK IN — time tracking by GSD HQ

Trust-based time tracking for freelancers and small agencies (1–10 people)
who bill by the hour. **No screenshots, no GPS, no activity monitoring —
ever.** Clock In assumes you trust the people you work with; it just makes
recording and reporting time painless. Clock in, do the work, clock out.

Built on the GSD HQ brand system: GSD Orange, Bebas Neue + Outfit, and zero
fluff.

## Features

- **Start/stop timer** and **manual entries** — both fully editable after the
  fact. Fixing yesterday's times takes seconds, not a support ticket.
- **Clients → Projects → Entries** hierarchy, with free-form tags.
- **Billable/non-billable** flag and per-project hourly rates. Each entry
  snapshots the rate it was tracked at, so changing a project's rate never
  rewrites history.
- **Reports**: summary by client/project over any date range (with
  per-currency totals), a weekly timesheet grid whose cells link straight to
  the underlying entries, and CSV export that honors the current filters.
- **Idle warning**: if a timer runs past your threshold (default 4 h), the
  dashboard asks whether to keep it, stop it, or discard it. That's the only
  "detection" in the app.
- **Two roles**: admins see and manage everything; members see their own
  time. Enforced in querysets, not hidden in templates.
- **Timezone-correct**: everything is stored in UTC and entered/displayed in
  each user's own timezone. Ambiguous or non-existent wall-clock times during
  DST changes are rejected with a clear error instead of silently guessed.

Deliberate non-goals for v1: invoicing, payments, integrations, mobile app,
automatic/AI tracking, approval workflows. (The schema is invoicing-ready —
see below.)

## Stack

Django 5.2 · SQLite (WAL mode) · server-rendered templates with a little
vanilla JS · WhiteNoise for static files · gunicorn · Docker.

## Quick start (Docker — recommended)

```bash
cp .env.example .env
# edit .env: set DJANGO_SECRET_KEY (see below) and your host
docker compose up --build
```

Generate a secret key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

The app migrates on startup and listens on <http://localhost:8000>.

First-run setup — create your admin account and (optionally) demo data:

```bash
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py seed_demo   # demo data, optional
```

A superuser created this way has Django-admin access; set its app role to
Admin under Team (or it defaults to member for app pages — easiest is to log
into `/admin/` once and set `role` there, or use the seeded admin).

### Demo logins (after `seed_demo`)

| user | role   | timezone         |
|------|--------|------------------|
| ana  | admin  | Asia/Manila      |
| ben  | member | America/New_York |
| mia  | member | Europe/Berlin    |

Password for all three: `demo-pass-1234`. Seeding is idempotent and safe to
re-run; it never touches a database that already has time entries.

## Quick start (local development)

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt    # Windows
# .venv/bin/pip install -r requirements.txt      # macOS/Linux

export DJANGO_DEBUG=1        # set DJANGO_DEBUG=1 on Windows (cmd)
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

## Configuration

All via environment variables (see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | — (required in prod) | Session/CSRF signing key |
| `DJANGO_DEBUG` | `0` | Never enable in production |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated hostnames |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | empty | Needed behind a proxy, e.g. `https://track.example.com` |
| `DJANGO_BEHIND_TLS` | `1` | Set `0` for plain-HTTP LAN deploys so cookies still work |
| `DJANGO_SSL_REDIRECT` | `0` | Set `1` to force HTTP→HTTPS at the app level |
| `DATA_DIR` | `./data` | Where the SQLite database lives |

## Deploying

Clock In is a single container with a single volume:

1. Put `docker-compose.yml`, `Dockerfile`, the source, and a filled-in `.env`
   on the host.
2. `docker compose up -d --build`.
3. Point a TLS-terminating reverse proxy (Caddy, nginx, Traefik) at port
   8000 and add your public origin to `DJANGO_CSRF_TRUSTED_ORIGINS`.
4. **Backups**: everything lives in `./data/`. Copy that directory (or just
   `db.sqlite3`) on a schedule and you're covered.

SQLite in WAL mode comfortably handles a 1–10 person team. If you outgrow
it, Django makes a Postgres migration straightforward — no schema changes
needed.

### Raspberry Pi / OpenMediaVault

Clock In runs fine on a Pi — the base image (`python:3.13-slim`) is
multi-arch, and the image builds natively on the Pi (first build takes a
few minutes).

1. In OMV, install **omv-extras** and the **openmediavault-compose** plugin
   (Services → Compose) if you haven't already.
2. Copy the project to the Pi (or `git clone`), e.g. into your appdata
   shared folder.
3. Create `.env` from `.env.example` and set — this part matters:

   ```ini
   DJANGO_SECRET_KEY=<generated key>
   DJANGO_DEBUG=0
   DJANGO_ALLOWED_HOSTS=<pi-ip>,<pi-hostname>,localhost
   DJANGO_CSRF_TRUSTED_ORIGINS=http://<pi-ip>:8000
   DJANGO_BEHIND_TLS=0          # REQUIRED for plain-HTTP LAN access
   ```

   `DJANGO_BEHIND_TLS=0` is the one people trip over: with it left at `1`,
   session cookies are marked Secure-only and **login silently fails over
   plain HTTP** — the browser just never sends the cookie.
4. Point the volume at real storage instead of the compose working dir if
   you prefer, e.g. in `docker-compose.yml`:

   ```yaml
   volumes:
     - /srv/dev-disk-by-uuid-XXXX/appdata/tempo/data:/app/data
   ```
5. In the Compose plugin, add the file and bring it **up** (or SSH in and
   run `docker compose up -d --build`). Port 8000 doesn't clash with the
   OMV web UI (port 80).
6. Create your admin user:
   `docker compose exec web python manage.py createsuperuser`
7. Back up the data directory with an OMV **Scheduled Job** or rsync task —
   that one folder is the entire application state.

On a Pi 3 (1 GB RAM), drop gunicorn to 2 workers in the `Dockerfile` CMD.
If you later expose Clock In beyond your LAN, put a TLS proxy in front
(Caddy/nginx/Traefik), switch `DJANGO_BEHIND_TLS=1`, set
`DJANGO_CSRF_TRUSTED_ORIGINS` to the public `https://` origin, and consider
`DJANGO_SSL_REDIRECT=1`.

## Tests

```bash
python manage.py test
```

69 tests cover the core promises: overlap detection semantics (half-open
intervals, adjacent entries don't conflict, running timers count), the
warn-then-confirm overlap flow, painless editing rules, timezone handling
(UTC storage, per-user display, DST spring-forward/fall-back including
rejection of ambiguous times), timer lifecycle (one running timer per user,
enforced by the database), role scoping on every page, and report/CSV math.

## Design notes

- **A running timer is just an entry with no end time.** One partial unique
  index guarantees at most one per user, and stopping a timer produces the
  same object a manual entry does — which is why editing is uniform and
  painless.
- **Overlaps are allowed but flagged.** Freelancers sometimes double-book on
  purpose; Clock In warns with the exact conflicting entries and lets you
  decide.
- **Invoicing-ready schema.** Entries snapshot `rate_applied`; clients carry
  a `currency`; amounts are never summed across currencies. An `Invoice`
  model can later reference entries without reshaping any existing data.
- **Archive, don't delete.** Clients and projects are protected from
  deletion at the database level (`PROTECT`); archiving hides them from
  pickers while keeping history intact. Users are deactivated, never
  deleted.

## Security

- Django's password hashing (PBKDF2), validators, and session auth
- CSRF protection on every form; state changes are POST-only
- Role checks in querysets and decorators (403/404, not hidden links)
- Secure cookies, HSTS-friendly settings, and `X-Frame-Options: DENY` when
  `DEBUG` is off
- No telemetry, no external requests: the app is fully self-contained
