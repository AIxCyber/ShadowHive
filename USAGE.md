# ShadowHive — Usage Guide

A comprehensive guide to using the ShadowHive platform: generating and deploying
realistic AI-generated company honeypots, managing the portal, and testing the
honeypot farm.

---

## Table of Contents

1. [Quick Start](#1-quick-start)
2. [Dashboard](#2-dashboard)
3. [Company Generation](#3-company-generation)
4. [Deploying a Company](#4-deploying-a-company)
5. [Portal](#5-portal)
6. [Event Ingestion](#6-event-ingestion)
7. [Threat Intelligence](#7-threat-intelligence)
8. [Honeypot Farm](#8-honeypot-farm)
9. [Authentication & User Management](#9-authentication--user-management)
10. [Development & Testing](#10-development--testing)
11. [Customization](#11-customization)

---

## 1. Quick Start

### Prerequisites

- Docker & Docker Compose
- 8GB+ RAM (16GB recommended for Ollama)

### Startup

```bash
# Clone and enter the project
git clone https://github.com/AIxCyber/ShadowHive.git
cd ShadowHive

# Start core services
docker compose up -d

# Wait ~30s for services to initialize
# Pull the default LLM model (first time only)
docker compose exec ollama ollama pull llama3.2:3b

# Access the dashboard
open http://localhost:3000
```

### Default Credentials

| User     | Password   | Role  |
|----------|-----------|-------|
| shadowhive | admin123 | admin |

You will be prompted to change the password on first login.

---

## 2. Dashboard

The frontend dashboard at http://localhost:3000 provides four main views:

### Company View (`/companies`)

- **Generate** a new company by selecting industry and size
- **Monitor** progress with a real-time progress bar showing each phase
- **Pause / Resume / Cancel** generation at any time
- **Save** profile templates for reuse
- **Toggle** infrastructure enrichment for deeper environments

### Honeypot View (`/attackers`)

- **Sessions** — see active and past SSH connections with IP addresses
- **Commands** — every command executed by attackers
- **Real-time** updates as events are ingested

### Intelligence View (`/intelligence`)

- **MITRE ATT&CK Map** — techniques and tactics mapped to attacker events
- **Threat Analysis** — severity distribution, timelines, IP geolocation
- **Attack Timelines** — chronological view of events per session

### Log Viewer (`/logs`)

- Filterable log table with level, logger, and search
- Auto-refresh support
- Aggregated stats by level and logger

---

## 3. Company Generation

### Via API

```bash
# Basic generation
curl -X POST "http://localhost:8000/api/companies/generate" \
  -H "Content-Type: application/json" \
  -d '{"industry":"Technology","size":"small"}'

# With overrides and security posture
curl -X POST "http://localhost:8000/api/companies/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "industry":"Healthcare",
    "size":"medium",
    "overrides":{
      "company_name":"MedSecure Labs",
      "description":"AI diagnostics biotech lab",
      "technologies":["Python","AWS","Docker"],
      "security_posture":"neglected"
    }
  }'

# With infrastructure enrichment
curl -X POST "http://localhost:8000/api/companies/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "industry":"Finance",
    "size":"large",
    "enrich":true
  }'
```

The POST returns a `task_id` immediately. Poll for progress:

```bash
curl -s "http://localhost:8000/api/companies/tasks/{task_id}" | jq .
```

### Via Dashboard

1. Open http://localhost:3000/companies
2. Select an **industry** and **size**
3. (Optional) Click the gear icon for Advanced Options:
   - Set a custom company name or description
   - Select a security posture
   - Enable Infrastructure Enrichment
   - Load a saved template
4. Click **Generate**
5. Watch the progress bar update through 4 phases (or 9 with enrichment)
6. Once complete, the company appears in the company list

### Task Lifecycle

```bash
# Pause a running generation
curl -X POST "http://localhost:8000/api/companies/tasks/{id}/pause"

# Resume a paused generation
curl -X POST "http://localhost:8000/api/companies/tasks/{id}/resume"

# Cancel a running generation
curl -X POST "http://localhost:8000/api/companies/tasks/{id}/cancel"

# Delete a task from history
curl -X DELETE "http://localhost:8000/api/companies/tasks/{id}"

# List all tasks
curl -s "http://localhost:8000/api/companies/tasks" | jq .
```

### Saved Templates

```bash
# Save a profile template
curl -X POST "http://localhost:8000/api/companies/profiles" \
  -H "Content-Type: application/json" \
  -d '{
    "name":"Healthcare Neglected",
    "industry":"Healthcare",
    "company_name":"MedSecure Labs",
    "technologies":["Python","AWS"],
    "security_posture":"neglected"
  }'

# List saved profiles
curl -s "http://localhost:8000/api/companies/profiles" | jq .

# Get a specific template
curl -s "http://localhost:8000/api/companies/profiles/{id}" | jq .

# Delete a template
curl -X DELETE "http://localhost:8000/api/companies/profiles/{id}"
```

### Generation Phases

| Phase | Progress | Description | Opt-in |
|-------|----------|-------------|--------|
| Profile | 0% → 10% | Company name, description, departments | Always |
| Employees | 10% → 35% | Personas with titles, emails, bios | Always |
| Emails | 35% → 60% | Internal email threads | Always |
| Documents | 60% → 85% | Reports, memos, specs | Always |
| Infrastructure | 85% → 90% | Servers, networks, cloud | ✓ toggle |
| Network Depth | 90% → 92% | DNS, load balancers, SSL, alerts | ✓ toggle |
| DevOps Pipeline | 92% → 93% | CI/CD configs, source leaks, Terraform | ✓ toggle |
| Security Config | 93% → 95% | Firewall rules, EDR, patch gaps, VPN | ✓ toggle |
| Attack Artifacts | 95% → 99% | Honeytokens, config leaks | ✓ toggle |

### Security Postures

| Posture | Effect |
|---------|--------|
| `default` | 1 plausible mid-market weakness |
| `mature` | Strong security, at most 1 minor issue |
| `startup` | Lean security — 1-2 weaknesses |
| `neglected` | Poor security — 2-3 weaknesses |

---

## 4. Deploying a Company

Once generated, deploy a company to make it live across:

- **Cowrie** — employee credentials become SSH login users, filesystem populated
- **Portal** — company website served on port 80

### Deploy

```bash
curl -X POST "http://localhost:8000/api/deploy/{company_id}"

# Check status
curl -s "http://localhost:8000/api/deploy/status" | jq .
```

### Undeploy

```bash
curl -X POST "http://localhost:8000/api/undeploy"
```

### What Deployment Creates

| Artifact | Location | Purpose |
|----------|----------|---------|
| `userdb.txt` | `honeypot_data/` | Cowrie auth — employee SSH creds |
| `contents/` | `honeypot_data/` | Realistic filesystem (home dirs, projects, `.ssh`) |
| `active_company.json` | `honeypot_data/` | Metadata consumed by the portal |

---

## 5. Portal

A standalone FastAPI + Jinja2 application serves a realistic fake company website
on **port 80**. It pulls live data from PostgreSQL.

The portal features a modern responsive design with Google Fonts (Inter), gradient
avatar initials, Unsplash background images, fade-in animations, social footer
links (LinkedIn, X, GitHub — plain text anchors, no `href="#"`), and a responsive
mobile layout. All HTML templates use CSS utility classes (zero inline styles
except hero background images). A standalone preview file at `portal/preview.html`
can be opened directly in a browser for CSS development. The SVG favicon is linked
directly from static (no separate route).

The portal is served behind nginx with two server blocks: port 80 for the public
portal, port 8080 for the admin dashboard. The admin login pre-fills `admin` as
the username (no hardcoded default credentials text), the sidebar uses
`javascript:void(0)` instead of `href="#"` for placeholder links, and a subtle
HTML comment hints at "debug endpoints pending cleanup" as a decoy. Blog labels
display the raw `doc_type` without a prefix.

### Public Pages

| Page | Description |
|------|-------------|
| `/` | Company landing page — hero with stats, team preview, services, insights (CSS utility classes, no inline styles) |
| `/about` | Company profile with office photos, department overview |
| `/team` | Employee directory with avatar initials and bios |
| `/careers` | Realistic job listings with salary ranges per department |
| `/blog` | Internal documents as blog-style articles |
| `/contact` | Working contact form (name, email, subject, message) + office hours — POST logs submissions as honeypot data |
| `/admin` | Admin dashboard with sidebar, metrics, email log, employee directory |

### Vulnerable/Decoy Endpoints (for attackers to discover)

| Endpoint | What It Leaks |
|----------|---------------|
| `/.env` | Environment secrets with realistic tokens (Sentry DSN, Slack bot tokens, AWS keys) |
| `/.git/config` | Repository metadata with embedded GitHub PAT (`ghp_*`) |
| `/.htaccess` | Apache config with legacy API redirect |
| `/composer.json` | PHP dependency file (Laravel + dev packages) |
| `/sitemap.xml` | XML sitemap listing all site paths |
| `/backup/` | Directory listing of fake SQL backup dumps |
| `/admin` | Admin dashboard — employee directory, metrics, email log |
| `/api/users` | Full user data dump (no auth) |
| `/api/orders` | Customer order data dump |
| `/robots.txt` | Honeytoken paths (disallows `/admin`, `/backup`) |
| `/update-profile` | Blind stored XSS via name/email/bio fields |

### Honeypot Login Pages (Credential Capture)

The portal also serves fake login pages that **capture credentials** to
`honeypot_logs/portal_honeypot.json`, ingested automatically:

| Path | Pretends To Be | Captures |
|------|---------------|----------|
| `/wp-login.php` | WordPress admin | username + password |
| `/phpmyadmin/` | Database manager | username + password |
| `/jenkins/` | CI/CD server | username + password |
| `/gitlab/` | Git repository | username + password |
| `/webmail/` | Email web client | email + password |
| `/vpn/` | VPN portal | username + password |
| `/api/v1/keys` | API key capture | Logs submitted keys (POST) |

### Testing Vulnerabilities

```bash
# Check for exposed .env with realistic tokens
curl http://localhost/.env

# Try admin panel
curl http://localhost/admin

# Browse the directory listing
curl http://localhost/backup

# Dump users
curl http://localhost/api/users

# Check for new decoy endpoints
curl http://localhost/.htaccess
curl http://localhost/composer.json
curl http://localhost/sitemap.xml

# Test honeypot login capture
curl -X POST http://localhost/wp-login.php \
  -d "log=admin&pwd=password123"

# Test working contact form
curl -X POST http://localhost/contact \
  -d "name=Attacker&email=test@evil.com&message=hello"
```

### How It Works

1. The portal reads `active_company.json` from the `honeypot_data` volume
2. It queries PostgreSQL for live company data (employees, departments, documents)
3. Each page renders Jinja2 templates with company-specific content
4. Job listings are dynamically generated from company departments with realistic titles, types, and salary bands
5. Vulnerable/decoy endpoints are served alongside the site, simulating a real-world staging environment with misconfigurations
6. Honeypot login pages and the contact form POST credentials to `_log_honeypot_event()`, which appends to `honeypot_logs/portal_honeypot.json` — the API's `HoneypotFileWatcher` polls this file every 30 seconds and ingests new events

### Customizing

The portal templates live in `portal/templates/` and static assets are in
`portal/static/`. You can modify them to change the company website appearance
or add new vulnerable endpoints. Refer to `portal/main.py` for the route definitions.

---

## 6. Event Ingestion

ShadowHive accepts events from any honeypot via the API. Both single and batch
payloads are supported in Cowrie-compatible JSON format.

```bash
# Single event
curl -X POST "http://localhost:8000/api/events" \
  -H "Content-Type: application/json" \
  -d '{
    "eventid": "cowrie.login.success",
    "src_ip": "192.168.1.100",
    "username": "admin",
    "password": "password123",
    "timestamp": "2025-01-01T00:00:00",
    "session": "abc123"
  }'

# Batch events
curl -X POST "http://localhost:8000/api/events" \
  -H "Content-Type: application/json" \
  -d '[
    {"eventid":"cowrie.login.success","src_ip":"10.0.0.1","username":"root","password":"toor","timestamp":"2025-01-01T00:00:00","session":"s1"},
    {"eventid":"cowrie.command.input","src_ip":"10.0.0.1","command":"cat /etc/passwd","timestamp":"2025-01-01T00:01:00","session":"s1"}
  ]'
```

Events are immediately visible in dashboard stats, sessions, and threat views.

### Background Watchers

The API runs background tasks that poll log files every 30 seconds:

| Watcher | Log Source | File Pattern |
|---------|-----------|--------------|
| HoneypotFileWatcher | opencanary.json | `opencanary.json` |
| HoneypotFileWatcher | portal_honeypot.json | Portal credential captures |
| HoneypotFileWatcher | wordpress.json | WordPress honeypot logs |
| HoneypotFileWatcher | cowrie2.json | Extra Cowrie instance |
| HoneypotFileWatcher | cowrie3.json | Extra Cowrie instance |
| CowrieClient | Cowrie REST API | HTTP poll |

---

## 7. Threat Intelligence

### Stats API

```bash
# Dashboard stats with configurable time range
curl -s "http://localhost:8000/api/stats?range=24h" | jq .
curl -s "http://localhost:8000/api/stats?range=7d" | jq .
curl -s "http://localhost:8000/api/stats?range=30d" | jq .
curl -s "http://localhost:8000/api/stats" | jq .  # defaults to 24h
```

### Threats

```bash
# All threats
curl -s "http://localhost:8000/api/threats" | jq .

# Filter by severity
curl -s "http://localhost:8000/api/threats?severity=high" | jq .

# Filter by MITRE tactic
curl -s "http://localhost:8000/api/threats?tactic=TA0001" | jq .
```

### Sessions

```bash
curl -s "http://localhost:8000/api/sessions" | jq .
```

Returns session data including `commands_executed` count and `duration_minutes`.

### Neo4j Attack Graph

```bash
# Get attack paths
curl -s "http://localhost:8000/api/graph/attack-paths" | jq .

# Get techniques
curl -s "http://localhost:8000/api/graph/techniques" | jq .

# Get IPs
curl -s "http://localhost:8000/api/graph/ips" | jq .
```

---

## 8. Honeypot Farm

Beyond the core Cowrie SSH honeypot, ShadowHive includes a multi-layered
honeypot farm. Enable it with:

```bash
docker compose --profile full up -d
```

### Available Honeypots

| Honeypot | Port(s) | What It Simulates |
|----------|---------|-------------------|
| Cowrie (main) | 2222 | SSH server with realistic filesystem |
| Cowrie2 | 2223 | Extra SSH instance (different config) |
| Cowrie3 | 2224 | Extra SSH instance (different config) |
| OpenCanary | 21,23,25,110,143,445,3306,3389,5900,8080,5060,69/udp | 12-protocol canary |
| Dionaea | 21,445,1433,3306,5060/5061,443 | Malware capture |
| WordPress | 8081 | Fake WordPress with log watcher |

### Cowrie Honeypot

The main Cowrie instance uses generated employee credentials:

```bash
# SSH into the honeypot (no password required — any user/pass works)
ssh -p 2222 any-user@localhost

# Or use a generated employee credential:
ssh -p 2222 jane.doe@localhost
# password: the employee's generated password
```

### OpenCanary

Listens on 12 protocols simultaneously. No interaction needed — scanning
triggers events automatically.

### Dionaea

Captures malware payloads from SMB, FTP, MSSQL, MySQL, SIP, and HTTP
connections. No interaction needed.

### WordPress Honeypot

```bash
# Browse the fake WordPress site
curl http://localhost:8081

# Submit a login (captured to wordpress.json)
curl -X POST http://localhost:8081/wp-login.php \
  -d "log=admin&pwd=password123"
```

---

## 9. Authentication & User Management

Auth is **enabled by default**. The default admin user is created on first startup.

### Login

Navigate to http://localhost:3000 and log in with:

- **Username:** shadowhive
- **Password:** admin123

You must change your password on first login.

### User Roles

| Role | Permissions |
|------|-------------|
| `admin` | Full access + user management |
| `user` | Generate + manage own data |
| `viewer` | Read-only access |

### Admin User Management

```bash
# List users
curl http://localhost:8000/api/admin/users \
  -H "Authorization: Bearer <token>"

# Create user
curl -X POST http://localhost:8000/api/admin/users \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"email":"new@example.com","password":"securepass123","role":"user"}'

# Force reset user password
curl -X POST http://localhost:8000/api/admin/users/{id}/reset-password \
  -H "Authorization: Bearer <token>"
```

### Disable Auth

```bash
# Set in .env:
AUTH_ENABLED=false

# Restart:
docker compose restart api
```

### Security Features

- **Rate limiting:** 10 requests per 60s per IP on auth endpoints
- **Account lockout:** 5 failed attempts = 15 min lockout
- **JWT validation:** Rejects secrets < 32 characters
- **Password policy:** Minimum 8 characters
- **Request tracing:** Unique `X-Request-ID` on every response
- **CORS hardening:** Restricted methods in production
- **Timezone support:** `X-Timezone` header for local timestamps

---

## 10. Development & Testing

### Local Development (No Docker)

```bash
# Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest tests/ -v --tb=short

# Lint
ruff check backend/ tests/

# Type check
mypy backend/

# Format
ruff format backend/ tests/

# Run all checks
make check-all
```

### Test Structure

Tests are in `tests/` and use async SQLite in-memory — no external database
needed. 165+ tests cover company generation, deployment, event ingestion,
threat intelligence, authentication, and the portal.

### Makefile Commands

```bash
make test         # Run all tests
make lint         # Run ruff linter
make typecheck    # Run mypy
make format       # Format code
make check-all    # lint + format + typecheck + test
make dev-install  # Install dev dependencies
```

---

## 11. Customization

### Portal Templates

Templates live in `portal/templates/` and use Jinja2 with CSS utility classes.
All 8 templates (index, about, team, careers, blog, contact, admin, base) were
rewritten to eliminate inline styles. To preview CSS changes without a server,
open `portal/preview.html` directly in a browser.

### Static Assets

CSS and favicon are in `portal/static/`. The stylesheet uses utility classes
for layout, typography, cards, buttons, and responsive breakpoints.

### Adding New Decoy Endpoints

1. Add a route in `portal/main.py`
2. Create or update the template in `portal/templates/`
3. Optionally add a `_log_honeypot_event()` call for credential capture

### AI Provider Configuration

Edit `configs/default.yaml` to configure AI routing:

```yaml
ai:
  default_provider: ollama
  routing:
    company_generation: ollama
    threat_analysis: openai  # Paid when analysis quality matters
```

### Environment Variables

Key `.env` variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_PASSWORD` | shadowhive | Database password |
| `NEO4J_PASSWORD` | shadowhive | Graph database password |
| `JWT_SECRET` | auto-generated | JWT signing secret (32+ chars) |
| `AUTH_ENABLED` | true | Enable/disable authentication |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `ANTHROPIC_API_KEY` | — | Anthropic API key |

---

## License

MIT
