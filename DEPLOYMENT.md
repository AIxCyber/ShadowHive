# ShadowHive — Deployment Guide

Comprehensive deployment instructions for all environments: local lab, production
single-host, multi-host / Docker Swarm, air-gapped / offline, and internet-facing
with TLS.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Prerequisites](#2-prerequisites)
3. [Quick Start — Single-Host Lab](#3-quick-start--single-host-lab)
4. [Production Deployment](#4-production-deployment)
5. [Multi-Host / Docker Swarm](#5-multi-host--docker-swarm)
6. [Air-Gapped Deployment](#6-air-gapped-deployment)
7. [Internet-Facing Deployment](#7-internet-facing-deployment)
8. [GPU Acceleration](#8-gpu-acceleration)
9. [Configuration Reference](#9-configuration-reference)
10. [Networking & Security](#10-networking--security)
11. [Storage & Backups](#11-storage--backups)
12. [Monitoring & Maintenance](#12-monitoring--maintenance)
13. [Troubleshooting](#13-troubleshooting)
14. [Reference](#14-reference)

---

## 1. Overview

ShadowHive is composed of **12 services** running in Docker containers (7 core + 5 opt-in honeypot farm with `profiles: ["full"]`):

| Service | Role | Base Image | Profile |
|---------|------|-----------|---------|
| `api` | FastAPI backend (company generation, task management, threat endpoints, event ingestion, deploy API) | `python:3.12-slim` | core |
| `frontend` | Next.js UI (company view, honeypot monitoring, intelligence dashboard, deploy controls) | `node:22-alpine` | core |
| `postgres` | PostgreSQL 16 — relational data (events, profiles, companies, company models) | `postgres:16-alpine` | core |
| `neo4j` | Neo4j 5 Community — graph data (relationships, attack paths) | `neo4j:5-community` | core |
| `ollama` | Local LLM hosting — generates all company content with zero API costs | `ollama/ollama` | core |
| `cowrie` | Main SSH honeypot — records attacker sessions, auto-ingested by API; uses injected employee credentials after deploy | `cowrie/cowrie` | core |
| `portal` | Fake company website (FastAPI + Jinja2) — realistic company pages with decoy endpoints, honeypot login pages, and professional UI (Google Fonts, social footer links to real domains, SVG favicon, animations, responsive design, CSS utility classes with zero inline styles). Blog labels show raw doc_type. Contact form POST logs submissions as honeypot data. Hidden HTML comment hints at "debug endpoints" as decoy. | `python:3.12-slim` | core |
| `cowrie2` | Second SSH honeypot instance — additional attack surface with separate config | `cowrie/cowrie` | full |
| `cowrie3` | Third SSH honeypot instance — additional attack surface with separate config | `cowrie/cowrie` | full |
| `opencanary` | Multi-protocol honeypot — FTP, Telnet, SMTP, POP3, IMAP, SMB, MySQL, RDP, VNC, HTTP Proxy, SIP, TFTP | `thinkst/opencanary` | full |
| `dionaea` | Malware capture honeypot — FTP, SMB, MSSQL, MySQL, SIP, HTTP, TFTP | `dinotools/dionaea` | full |
| `wordpress` | Fake WordPress honeypot — vulnerable wp-config.php + Apache log watcher | custom (`wordpress/Dockerfile`) | full |

### Deployment Scenarios

| Scenario | Description | Best For |
|----------|-------------|----------|
| **Single-host lab** | All containers on one machine, plain HTTP, local network | Development, testing, internal demos |
| **Production** | Hardened containers, resource limits, health checks, read-only fs | Team deployments, controlled environments |
| **Multi-host / Swarm** | Services distributed across nodes (GPU host for Ollama, storage host for DBs) | Scale-out, high availability |
| **Air-gapped** | Pre-downloaded images and models, no internet required | Classified networks, offline labs |
| **Internet-facing** | TLS via nginx/Caddy, rate limiting, security headers, restricted CORS | External attacker engagement, CTF |
| **GPU-accelerated** | NVIDIA GPU passthrough to Ollama for faster generation | Any scenario where latency matters (3-5x speedup) |

### Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                          REVERSE PROXY                               │
│              nginx or Caddy (TLS, rate limiting, headers)             │
│              binds :80/:443, proxies to internal network              │
└──────────────────────┬───────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                             DOCKER BRIDGE NETWORK                                     │
│                                                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐  ┌──────┐      │
│  │   api    │  │ frontend │  │ postgres │  │  neo4j   │  │ portal │  │ollama│      │
│  │ :8000    │  │ :3000    │  │ :5432    │  │:7474/7687│  │ :8001  │  │:11434│      │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └───┬────┘  └──┬────┘      │
│       │             │             │             │            │          │           │
│       └─────────────┴──────┬──────┴──────┬──────┴────────────┘          │           │
│                            │             │                              │           │
│                     ┌──────┴──────┐ ┌────┴─────┐   ┌──────────────────┐ │           │
│                     │  pgdata     │ │ neodata  │   │ honeypot_data    │ │           │
│                     │  (volume)   │ │ (volume) │   │ (shared volume)  │ │           │
│                     │             │ │          │   │ cowrie + portal  │ │           │
│                     └─────────────┘ └──────────┘   └──────────────────┘ │           │
│                                                                         │           │
│                     ┌──────────────────────────────────────────────────┐ │           │
│                     │              ollamadata (volume)                 │◄┘           │
│                     └──────────────────────────────────────────────────┘             │
│                                                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────────┐      │
│  │ opencanary│  │ dionaea  │  │ cowrie2  │  │ cowrie3  │  │   wordpress     │      │
│  │12 protocols│  │malware   │  │SSH:2223  │  │SSH:2224  │  │  :8081          │      │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └─────────────────┘      │
│       │              │             │             │               │                 │
│       └──────────────┴─────────────┴─────────────┴───────────────┘                 │
│                              │                                                    │
│                     ┌────────┴────────┐                                            │
│                     │  honeypot_logs  │  (shared host bind mount)                  │
│                     │  opencanary.json│                                            │
│                     │  cowrie2.json   │                                            │
│                     │  cowrie3.json   │                                            │
│                     │  portal_honeypot.json                                        │
│                     │  wordpress.json  │                                            │
│                     └─────────────────┘                                            │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

**Communication flow:**
- All internal traffic goes over the Docker bridge network (no host networking)
- Frontend proxies `/api/*` requests to the API container via Next.js rewrites
- API connects to Postgres (port 5432), Neo4j (bolt://neo4j:7687), and Ollama (http://ollama:11434)
- Portal connects to Postgres (port 5432) for live company data during deploy
- Cowrie and Portal share the `honeypot_data` volume (userdb.txt, filesystem contents, metadata)
- API, Cowrie2, Cowrie3, OpenCanary, Dionaea, WordPress, and Portal all share the `honeypot_logs` host bind mount — all honeypot events are written as JSON-line files and periodically ingested by the API's `HoneypotFileWatcher`
- API ingests from Cowrie main via `CowrieClient` (HTTP polling of Cowrie REST API) and from all other honeypots via `HoneypotFileWatcher` (JSON file polling from `honeypot_logs/`)
- Reverse proxy (nginx/Caddy) is the **only** service that binds host ports 80/443
- Postgres, Neo4j, and Ollama ports are never exposed to the host in production
- API and Frontend ports bind to `127.0.0.1` in production (only accessible through the proxy)
- New honeypot farm services use `profiles: ["full"]` and are opt-in with `docker compose --profile full up -d`

---

## 2. Prerequisites

### Hardware Requirements

| Component | Minimum | Recommended (Lab) | Recommended (Production) |
|-----------|---------|-------------------|--------------------------|
| **CPU** | 2 cores | 4 cores | 8+ cores |
| **RAM** | 8 GB | 16 GB | 32 GB |
| **Disk** | 20 GB free | 50 GB SSD | 100 GB+ SSD |
| **GPU** | — | — | NVIDIA with 8GB+ VRAM (optional) |

RAM breakdown by scenario:
- **Base (all services):** ~4 GB (Postgres 256MB, Neo4j 512MB, Ollama 2GB, API 256MB, Frontend 128MB)
- **Ollama with 3B model:** +2 GB
- **Ollama with 7B model:** +6 GB
- **Ollama with 13B model:** +10 GB
- **Generation peak:** Ollama can spike to 2-4x base RAM during generation

### Software Requirements

| Software | Version | Required For |
|----------|---------|-------------|
| **Docker** | 24+ | All scenarios |
| **Docker Compose** | v2 (plugin) | All scenarios |
| **NVIDIA Container Toolkit** | Latest | GPU acceleration |
| **Git** | Latest | Cloning the repository |

### Network Requirements

| Port | Service | Internal | Host (Lab) | Host (Prod) | Notes |
|------|---------|----------|------------|-------------|-------|
| 80 | nginx/Caddy | — | ✓ | ✓ | HTTP (redirects to HTTPS in prod) |
| 443 | nginx/Caddy | — | ✗ | ✓ | HTTPS with TLS |
| 3000 | Frontend | ✓ | ✓ (dev) | ✗ | Never expose directly in prod |
| 8000 | API | ✓ | ✓ (dev) | ✗ | Never expose directly in prod |
| 5432 | PostgreSQL | ✓ | ✗ | ✗ | Internal only |
| 7474 | Neo4j HTTP | ✓ | ✓ (dev) | ✗ | Browser-based graph viewer |
| 7687 | Neo4j Bolt | ✓ | ✗ | ✗ | Internal only |
| 11434 | Ollama | ✓ | ✗ | ✗ | Internal only |
| 2222 | Cowrie SSH | — | ✓ | ✓ (change to 22) | Honeypot — any SSH client can connect |
| 8080 | Cowrie API | ✓ | ✗ | ✗ | REST API for ShadowHive polling |

### Required Reading

Before deploying, understand:
- The generation pipeline takes **5-12 minutes** on CPU (Ollama with 3B model) — this is normal
- All enrichment phases are **opt-in** via a checkbox in the UI
- Dpshared models are ~2 GB each (download once)
- The `security_posture` setting controls how many deliberate weaknesses appear

---

## 3. Quick Start — Single-Host Lab

This is the fastest way to get ShadowHive running on a single machine for
development, testing, or internal demos. No TLS, no hardening — just a working
stack.

### 3.1 Clone the Repository

```bash
git clone https://github.com/AIxCyber/ShadowHive.git
cd shadowhive
```

### 3.2 Configure Environment

```bash
cp .env.example .env
```

Edit `.env` to set strong passwords if this is accessible on a network:

```bash
# Required: change these in any multi-user environment
POSTGRES_PASSWORD=your-strong-password-here
NEO4J_PASSWORD=your-other-strong-password-here

# Optional: enable paid AI providers
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
```

### 3.3 Start All Services

```bash
# Start core services (API, frontend, databases, Cowrie, portal)
docker compose up -d

# (Optional) Start the full honeypot farm — adds OpenCanary, Dionaea,
# Cowrie2, Cowrie3, and WordPress honeypot containers
docker compose --profile full up -d
```

This starts the core containers. The first pull/build may take a few minutes.
Honeypot farm services are opt-in via the `--profile full` flag.

Verify all services are running:

```bash
docker compose ps
```

Expected output (all `Up` or `healthy`):

```
NAME                    STATUS
shadowhive-api-1        Up 2 minutes (healthy)
shadowhive-frontend-1   Up 2 minutes (healthy)
shadowhive-postgres-1   Up 2 minutes (healthy)
shadowhive-neo4j-1      Up 2 minutes (healthy)
shadowhive-ollama-1     Up 2 minutes
shadowhive-cowrie-1     Up 2 minutes
```

### 3.4 Pull the LLM Model

ShadowHive defaults to `llama3.2:3b` (~2 GB). Pull it now so generation
doesn't time out on first use:

```bash
docker compose exec ollama ollama pull llama3.2:3b
```

> **Tip:** If you have limited RAM, use `llama3.2:1b` instead.
> Edit `configs/default.yaml` and change `default_model` accordingly.

### 3.5 Verify the Installation

```bash
# Health check endpoint
curl -s http://localhost:8000/api/companies/health

# Frontend responds
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
```

Both should return `200`.

### 3.6 Generate Your First Company

```bash
curl -X POST "http://localhost:8000/api/companies/generate" \
  -H "Content-Type: application/json" \
  -d '{"industry":"Technology","size":"small"}'
```

This returns a `task_id`. Poll for completion:

```bash
curl -s "http://localhost:8000/api/companies/tasks/TASK_ID" | jq .
```

Or open the UI at **http://localhost:3000/companies** and watch the progress bar.

### 3.7 Quick Teardown

```bash
# Stop everything
docker compose down

# Stop and delete all data (volumes included)
docker compose down -v
```

---

## 4. Production Deployment

This section builds on Quick Start with hardening, resource limits, health
checks, and a reverse proxy. Suitable for team-accessible deployments.

### 4.1 Docker Build Targets

Both the backend and frontend have **two-stage Dockerfiles**:

| Stage | Backend | Frontend |
|-------|---------|----------|
| `dev` | Single worker, dev dependencies installed (default) | `npm run dev` with hot-reload |
| `prod` | 4 workers, non-root user, health check | `npm run build` + `npm run start`, non-root user |

By default, `docker compose up` builds the `dev` target. For production, use:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

The production override:
- Builds the `prod` stage for both API and frontend
- Binds API/Frontend ports to `127.0.0.1` only (not accessible from other hosts)
- Sets resource limits (CPU/memory)
- Enables health checks with restart policies
- Sets `read_only: true` with `tmpfs` for writable `/tmp`
- Drops all Linux capabilities for API and Frontend containers
- Mounts `configs/` as read-only

### 4.2 Production Compose Override

File: `docker-compose.prod.yml`

```yaml
services:
  api:
    build:
      target: prod
    ports:
      - "127.0.0.1:8000:8000"
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 512M
    read_only: true
    cap_drop:
      - ALL
    tmpfs:
      - /tmp
    security_opt:
      - no-new-privileges:true
  # ... (full file in repository)
```

> **Security note:** The `read_only: true` flag prevents an attacker who gains
> code execution in the container from writing malicious files. Combined with
> `cap_drop: ALL` and `no-new-privileges:true`, container escape is much harder.

### 4.3 Reverse Proxy

**You have two choices: nginx or Caddy.**

#### Option A: nginx (more features, manual TLS)

The project includes a hardened nginx config at `nginx/nginx.conf` with **two server blocks**:
- **Port 80** — public-facing portal (routes to `shadowhive_portal` upstream, port 8001)
- **Port 8080** — admin dashboard + API (routes to frontend and API upstreams, with WebSocket support and static asset caching)

Additional security features:
- Security headers (HSTS, CSP, X-Frame-Options, X-Content-Type-Options)
- Rate limiting on all API endpoints (30 req/s general, 2 req/min for generation)
- Body size limits (10 MB)
- Connection limits
- Request buffering disabled
- Deny access to internal service paths (`/neo4j/`, `/ollama/`, `/.env`, `/.git/`)
- Static asset caching (365 days)
- WebSocket support for Next.js HMR (dev mode)

**To use nginx with plain HTTP (internal):**
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  -f docker-compose.nginx.yml up -d
```

The nginx container listens on port 80. Access the UI at `http://your-host/`.

**To use nginx with TLS (internet-facing):**

1. Install certbot and get a certificate:
   ```bash
   certbot certonly --nginx -d your-domain.com
   ```

2. Uncomment the TLS server block in `nginx/nginx.conf` and update the
   certificate paths.

3. Uncomment port 443 in `docker-compose.nginx.yml` and mount certificates:
   ```yaml
   services:
     nginx:
       ports:
         - "80:80"
         - "443:443"
       volumes:
         - /etc/letsencrypt:/etc/letsencrypt:ro
   ```

4. Restart:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml \
     -f docker-compose.nginx.yml up -d
   ```

#### Option B: Caddy (simpler, auto TLS)

Caddy automatically provisions Let's Encrypt certificates — no certbot needed.

File: `Caddyfile`

**To use Caddy with a real domain:**
```bash
# Edit Caddyfile and replace your-domain.com
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  -f docker-compose.caddy.yml up -d
```

Caddy automatically:
- Detects the domain and gets a Let's Encrypt certificate
- Redirects HTTP to HTTPS
- Applies TLS 1.3 with modern ciphers
- Renews certificates automatically

**To use Caddy for local/lab (no domain):**
Comment out the TLS block in `Caddyfile` and uncomment the `:80` section.

### 4.4 .env for Production

```bash
# Mandatory: change these
POSTGRES_PASSWORD=$(openssl rand -base64 32)
NEO4J_PASSWORD=$(openssl rand -base64 32)

# Optional: paid AI providers
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

> **⚠ Security:** Never commit `.env` to version control. Set file permissions:
> ```bash
> chmod 600 .env
> ```

### 4.5 Production Startup Command

```bash
# Without reverse proxy
make PROFILE=prod up

# With nginx
make PROFILE=prod up && \
  docker compose -f docker-compose.yml -f docker-compose.prod.yml \
    -f docker-compose.nginx.yml up -d

# With Caddy
make PROFILE=prod up && \
  docker compose -f docker-compose.yml -f docker-compose.prod.yml \
    -f docker-compose.caddy.yml up -d
```

---

## 5. Multi-Host / Docker Swarm

For deployments across multiple machines, Docker Swarm provides built-in
orchestration, secrets management, and overlay networking.

### 5.1 Service Placement Strategy

| Service | Placement | Rationale |
|---------|-----------|-----------|
| `ollama` | GPU host | Needs NVIDIA GPU for acceleration |
| `postgres` | Storage host | Persistent volume on fast SSD |
| `neo4j` | Storage host | Persistent volume, benefits from RAM |
| `api` | Any worker | Stateless, scales horizontally |
| `frontend` | Any worker | Stateless, scales horizontally |
| `nginx` / `caddy` | Ingress host | Exposed to external traffic |

### 5.2 Swarm Stack File

Create a `docker-stack.yml`:

```yaml
version: "3.8"

services:
  api:
    image: shadowhive-api:latest
    build:
      target: prod
    ports:
      - target: 8000
        published: 8000
        mode: host
    environment:
      POSTGRES_PASSWORD: /run/secrets/db_password
      NEO4J_PASSWORD: /run/secrets/neo4j_password
    secrets:
      - db_password
      - neo4j_password
    deploy:
      replicas: 2
      resources:
        limits:
          memory: 2G
      placement:
        constraints:
          - node.role == worker

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: shadowhive
      POSTGRES_USER: shadowhive
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    secrets:
      - db_password
    volumes:
      - pgdata:/var/lib/postgresql/data
    deploy:
      placement:
        constraints:
          - node.labels.storage == true

  # ... other services follow the same pattern

secrets:
  db_password:
    external: true
  neo4j_password:
    external: true

volumes:
  pgdata:
    driver: rexray/rbd  # or your preferred storage driver
  neodata:
    driver: rexray/rbd
  ollamadata:
    driver: rexray/rbd
```

### 5.3 Deploy to Swarm

```bash
# Create secrets
echo "your-db-password" | docker secret create db_password -
echo "your-neo4j-password" | docker secret create neo4j_password -

# Deploy stack
docker stack deploy -c docker-stack.yml shadowhive

# Verify
docker stack services shadowhive

# Scale API
docker service scale shadowhive_api=3

# Update a service
docker service update --image shadowhive-api:v2 shadowhive_api
```

### 5.4 Shared Storage

For Swarm, ensure your storage driver supports `ReadWriteMany`:

- **NFS:** Simple, widely supported
- **Rook/Ceph:** Recommended for production
- **Portworx:** Enterprise option
- **Local volumes with constraints:** Simple but limits placement

---

## 6. Air-Gapped Deployment

For networks without internet access.

### 6.1 Pre-Pull Everything

On a connected machine:

```bash
# Pull images
docker compose pull

# Pull the LLM model
docker compose exec ollama ollama pull llama3.2:3b

# Save images to tar files
docker save shadowhive-api:latest -o shadowhive-api.tar
docker save shadowhive-frontend:latest -o shadowhive-frontend.tar
docker save postgres:16-alpine -o postgres.tar
docker save neo4j:5-community -o neo4j.tar
docker save ollama/ollama:latest -o ollama.tar

# Copy Ollama model data
docker run --rm -v ollamadata:/data alpine tar czf ollama-models.tar.gz -C /data .
```

### 6.2 Transfer to Air-Gapped Network

Copy the `.tar` files and `ollama-models.tar.gz` via USB drive or approved
transfer method.

### 6.3 Load Offline

```bash
docker load -i shadowhive-api.tar
docker load -i shadowhive-frontend.tar
docker load -i postgres.tar
docker load -i neo4j.tar
docker load -i ollama.tar

# Restore Ollama model data
docker run --rm -v ollamadata:/data alpine tar xzf ollama-models.tar.gz -C /data
```

### 6.4 Disable Internet-Dependent Features

In `configs/default.yaml`, set fallback to single provider:

```yaml
ai:
  default_provider: ollama
  fallback:
    enabled: false  # No cascade to paid providers
```

Verify that no configuration references external URLs (paid APIs are disabled
by default if their keys are empty).

### 6.5 Verify No Call-Home

```bash
# Check for any outbound connections from running containers
docker compose exec api curl -s --connect-timeout 3 https://www.google.com
# Should fail or timeout
```

---

## 7. Internet-Facing Deployment

For exposing ShadowHive to external attackers. This requires TLS, strict rate
limiting, and continuous monitoring.

### 7.1 Prerequisites

- A registered domain (e.g., `shadowhive.your-org.com`)
- DNS record pointing to the server's public IP
- Ports 80 and 443 open in the firewall (and only those ports)
- A firewall in front of the server (cloud firewall or hardware appliance)

### 7.2 Recommended Stack

```
Internet ──► Cloud Firewall ──► nginx/Caddy (TLS) ──► Frontend + API
                              (only 80, 443 open)    (internal network)
```

### 7.3 Firewall Rules

```bash
# Allow only HTTP(S) from anywhere
iptables -A INPUT -p tcp --dport 80 -j ACCEPT
iptables -A INPUT -p tcp --dport 443 -j ACCEPT

# Block everything else from outside
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A INPUT -i lo -j ACCEPT
iptables -A INPUT -j DROP
```

### 7.4 Rate Limiting

The nginx config (`nginx/nginx.conf`) includes rate limiting:

```nginx
# General API: 30 requests/second per IP
limit_req zone=api burst=20 nodelay;

# Generation endpoint: 2 requests/minute per IP (expensive LLM calls)
limit_req zone=generate burst=1 nodelay;
```

The Caddyfile includes equivalent rate limiting via the `rate_limit` directive.

### 7.5 Security Headers

Both nginx and Caddy configs include these security headers:

| Header | Value | Purpose |
|--------|-------|---------|
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains` | Force HTTPS, prevent SSL stripping |
| `X-Frame-Options` | `SAMEORIGIN` | Prevent clickjacking |
| `X-Content-Type-Options` | `nosniff` | Prevent MIME-type sniffing |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Control referrer data |
| `Content-Security-Policy` | see config | Prevent XSS and data injection |
| `Permissions-Policy` | restricted | Disable browser APIs (camera, mic, etc.) |

### 7.6 What NOT to Do

| Anti-pattern | Why |
|-------------|-----|
| Expose Postgres (5432) to the internet | Direct database access, no auth required |
| Expose Neo4j (7474/7687) to the internet | Browser-accessible graph viewer, no auth |
| Expose Ollama (11434) to the internet | Anyone can query your LLM ($$$ if paid model) |
| Run without TLS | Credentials, API keys, and generated data sent in plaintext |
| Use default passwords | Trivial to guess and immediately compromise |
| Use `--net=host` | Breaks container isolation, exposes all ports |
| Skip rate limiting | DoS via free generation endpoint |

### 7.7 If the Container Is Compromised

The production configuration is designed to limit blast radius:

| Defense | What It Prevents |
|---------|-----------------|
| `read_only: true` | Attacker can't write malware to the filesystem |
| `cap_drop: ALL` | Can't change network config, load kernel modules, or use `ptrace` |
| `no-new-privileges:true` | Can't escalate via setuid binaries |
| `tmpfs: /tmp` | Writable temp directory but no persistence |
| No host port exposure for DBs | Can't pivot to database from outside |
| Non-root user | Default user has no sudo, limited permissions |

Even with these defenses, an attacker who gains code execution can:
- Read environment variables (database passwords) — **use Docker secrets in Swarm**
- Make outgoing connections from the container — **use egress firewalls**
- Access other containers on the same Docker network — **but not the host**
- Modify application data in the database — **but can't drop tables from the read-only API**

For maximum security: run behind a WAF, use egress filtering, and monitor
container logs for suspicious activity.

### 7.8 Fail2Ban (Optional)

Install fail2ban on the host to block IPs that hit non-existent paths:

```ini
# /etc/fail2ban/jail.local
[shadowhive-nginx]
enabled = true
port = http,https
filter = shadowhive-nginx
logpath = /var/log/nginx/shadowhive-access.log
maxretry = 10
bantime = 3600
```

---

## 8. GPU Acceleration

Ollama supports NVIDIA GPUs for dramatically faster text generation.
Expect 3-5x speedup on a modern GPU.

### 8.1 Prerequisites

- NVIDIA GPU with 8GB+ VRAM (tested on RTX 3070/3080/4090, A100, V100)
- NVIDIA drivers installed on the host
- NVIDIA Container Toolkit installed

```bash
# Install the NVIDIA Container Toolkit (Ubuntu/Debian)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

### 8.2 Start with GPU

```bash
# Development with GPU
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d

# Production with GPU
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  -f docker-compose.gpu.yml up -d
```

### 8.3 Verify GPU Access

```bash
# Check GPU is visible inside Ollama
docker compose exec ollama nvidia-smi

# Or ask Ollama
docker compose exec ollama ollama list
```

### 8.4 Model Selection for GPU

| Model | VRAM | CPU Speed | GPU Speed | Quality |
|-------|------|-----------|-----------|---------|
| `llama3.2:1b` | — | Fast | Very fast | Basic |
| `llama3.2:3b` | — | Slow | Fast | Good |
| `llama3.1:8b` | 6 GB | Very slow | Medium | Better |
| `llama3.1:70b` | 40 GB | Impractical | Slow (multi-GPU) | Best |

Edit `configs/default.yaml` to change the model:

```yaml
ai:
  providers:
    ollama:
      default_model: llama3.1:8b  # Use 8B on GPU
```

> **Note:** Even with GPU, generation takes 30-90 seconds per phase.
> This is due to context size and prompt engineering, not raw throughput.

---

## 9. Configuration Reference

### 9.1 Environment Variables (`.env`)

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `POSTGRES_PASSWORD` | `shadowhive` | Yes | PostgreSQL password |
| `NEO4J_PASSWORD` | `shadowhive` | Yes | Neo4j password |
| `OPENAI_API_KEY` | — | No | OpenAI API key (paid provider) |
| `ANTHROPIC_API_KEY` | — | No | Anthropic API key (paid provider) |
| `AUTH_ENABLED` | `true` (in compose) | No | Set to `false` to disable auth |
| `AUTH_MODE` | `jwt` | No | Auth mode (`none`, `api_key`, `jwt`) |
| `JWT_SECRET` | — | If auth enabled | HMAC signing key (use a long random string) |
| `SMTP_HOST` | — | If email reset needed | SMTP server hostname |
| `SMTP_PORT` | `587` | No | SMTP server port |
| `SMTP_USERNAME` | — | If SMTP requires auth | SMTP username |
| `SMTP_PASSWORD` | — | If SMTP requires auth | SMTP password |
| `SMTP_FROM` | `noreply@shadowhive.local` | No | From address for password reset emails |

### 9.2 AI Provider Configuration (`configs/default.yaml`)

```yaml
ai:
  default_provider: ollama
  providers:
    ollama:
      base_url: http://ollama:11434
      default_model: llama3.2:3b
      timeout: 600              # 10 min — Ollama is slow on CPU
    openai:
      api_key: ${OPENAI_API_KEY}
      default_model: gpt-4o
      timeout: 60               # 1 min — OpenAI is fast
    anthropic:
      api_key: ${ANTHROPIC_API_KEY}
      default_model: claude-sonnet-4-20250514
      timeout: 60
  routing:
    company_generation: ollama   # Free for bulk work
    threat_analysis: ollama      # Switch to openai for better quality
  fallback:
    enabled: true
    order: [ollama, openai, anthropic]
    cascade_on_error: true
    cascade_on_timeout: true
```

**Key settings to tune:**

| Setting | Recommend | Notes |
|---------|-----------|-------|
| `ollama.default_model` | `llama3.2:3b` | Good balance of speed and quality |
| `ollama.timeout` | 600 | LLM generation takes 30-90s per phase |
| `routing.threat_analysis` | `ollama` → `openai` | Switch to paid for better threat analysis |
| `fallback.enabled` | `true` | Auto-failover if Ollama is down |

### 9.3 Database Configuration

```yaml
database:
  postgresql:
    host: postgres
    port: 5432
    database: shadowhive
    user: shadowhive
    password: ${POSTGRES_PASSWORD}
    pool_size: 10
  neo4j:
    uri: bolt://neo4j:7687
    user: neo4j
    password: ${NEO4J_PASSWORD}
```

These defaults work with the Docker Compose setup. Change `host` to point to
external databases if needed.

### 9.4 Authentication Configuration

```yaml
auth:
  enabled: ${AUTH_ENABLED:true}     # Default: on. Set AUTH_ENABLED=false to disable.
  mode: ${AUTH_MODE:jwt}            # none | api_key | jwt
  jwt:
    secret: ${JWT_SECRET:}          # HMAC-SHA256 key; empty = ephemeral key
    algorithm: HS256
    access_token_expire_minutes: 60
    refresh_token_expire_days: 30
    min_secret_length: 32           # Rejected at startup if shorter
  rate_limiting:
    enabled: true
    max_requests: 10                # Per window
    window_seconds: 60              # Per IP, on /register /login /change-password
  lockout:
    max_attempts: 5                 # Failed logins before lockout
    lockout_minutes: 15
  password_policy:
    min_length: 8                   # Minimum password characters
  smtp:
    host: ${SMTP_HOST:}             # Set for production password reset emails
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME:}
    password: ${SMTP_PASSWORD:}
    from: ${SMTP_FROM:noreply@shadowhive.local}
    tls: true
  api_key: ${API_KEY:}
```

**Important notes:**

| Setting | Note |
|---------|------|
| `auth.enabled` | Defaults to `true`; set `AUTH_ENABLED=false` to disable |
| `jwt.secret` empty | An ephemeral random key is generated on each startup — all existing sessions are invalidated on restart. **Required for production.** Must be 32+ characters (validated at startup). |
| `jwt.min_secret_length` | If a configured secret is shorter than this, the API logs a warning and refuses to start |
| `smtp.host` empty | Password reset tokens are logged to console (dev mode) instead of emailed |

**RBAC roles:**

| Role | Permissions |
|------|-------------|
| `admin` | Full access — generate companies, view all data, manage users |
| `user` | Generate companies, view own data |
| `viewer` | Read-only — view dashboards and data |

**Default admin** (created on first startup): `shadowhive` / `admin123` — the user is forced to change password on first login.

### 9.5 Server Configuration

```yaml
server:
  host: 0.0.0.0
  port: 8000
  debug: true            # Set to false in production
  cors_origins:
    - http://localhost:3000
```

In production, set `debug: false` and restrict `cors_origins` to your domain:

```yaml
server:
  debug: false
  cors_origins:
    - https://shadowhive.your-domain.com
```

---

## 10. Networking & Security

### 10.1 Port Matrix

| Port | Service | Internal | Lab Host | Prod Host | Why |
|------|---------|----------|----------|-----------|-----|
| 80 | Reverse proxy | — | ✓ | ✓ | HTTP (redirect) |
| 443 | Reverse proxy | — | ✗ | ✓ | HTTPS |
| 3000 | Frontend | ✓ | ✓ | `127.0.0.1` | Dev access only |
| 8000 | API | ✓ | ✓ | `127.0.0.1` | Dev access only |
| 5432 | PostgreSQL | ✓ | ✗ | ✗ | Direct DB access not needed |
| 7474 | Neo4j HTTP | ✓ | ✓ | `127.0.0.1` | Graph browser |
| 7687 | Neo4j Bolt | ✓ | ✗ | ✗ | Internal only |
| 11434 | Ollama | ✓ | ✗ | ✗ | No external access needed |
| 80 | Portal | — | ✓ | ✓ | Company website (fake staging site) + honeypot login pages |
| 8001 | Portal internal | ✓ | ✗ | ✗ | Internal FastAPI endpoint |
| 2222 | Cowrie main SSH | — | ✓ | ✓ | Primary SSH honeypot |
| 2223 | Cowrie2 SSH | — | ✓ | ✓ (profile full) | Secondary SSH honeypot |
| 2224 | Cowrie3 SSH | — | ✓ | ✓ (profile full) | Tertiary SSH honeypot |
| 21 | OpenCanary FTP | — | ✓ | ✓ (profile full) | FTP honeypot |
| 23 | OpenCanary Telnet | — | ✓ | ✓ (profile full) | Telnet honeypot |
| 25 | OpenCanary SMTP | — | ✓ | ✓ (profile full) | SMTP honeypot |
| 110 | OpenCanary POP3 | — | ✓ | ✓ (profile full) | POP3 honeypot |
| 143 | OpenCanary IMAP | — | ✓ | ✓ (profile full) | IMAP honeypot |
| 445 | OpenCanary SMB | — | ✓ | ✓ (profile full) | SMB honeypot |
| 3306 | OpenCanary MySQL | — | ✓ | ✓ (profile full) | MySQL honeypot |
| 3389 | OpenCanary RDP | — | ✓ | ✓ (profile full) | RDP honeypot |
| 5900 | OpenCanary VNC | — | ✓ | ✓ (profile full) | VNC honeypot |
| 8080 | OpenCanary HTTP Proxy | — | ✓ | ✓ (profile full) | HTTP proxy honeypot |
| 5060 | OpenCanary/Dionaea SIP | — | ✓ | ✓ (profile full) | SIP honeypot |
| 69/udp | OpenCanary TFTP | — | ✓ | ✓ (profile full) | TFTP honeypot |
| 135 | Dionaea SMB | — | ✓ | ✓ (profile full) | SMB over TCP |
| 443 | Dionaea HTTPS | — | ✓ | ✓ (profile full) | HTTPS honeypot |
| 1433 | Dionaea MSSQL | — | ✓ | ✓ (profile full) | MSSQL honeypot |
| 8081 | WordPress honeypot | — | ✓ | ✓ (profile full) | Fake WordPress site |
| 42 | Dionaea WINS | — | ✓ | ✓ (profile full) | WINS honeypot |
| 5061 | Dionaea SIP/TLS | — | ✓ | ✓ (profile full) | SIP over TLS |

### 10.2 Firewall Rules Template

```bash
#!/bin/bash
# iptables rules for ShadowHive production host

# Flush existing rules
iptables -F
iptables -X

# Default policies
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT ACCEPT

# Allow loopback
iptables -A INPUT -i lo -j ACCEPT

# Allow established connections
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

# Allow HTTP and HTTPS
iptables -A INPUT -p tcp --dport 80 -j ACCEPT
iptables -A INPUT -p tcp --dport 443 -j ACCEPT

# Allow SSH (limit by IP if possible)
iptables -A INPUT -p tcp --dport 22 -j ACCEPT

# Deny everything else
iptables -A INPUT -j LOG --log-prefix "SHADOWHIVE-DROP: "
iptables -A INPUT -j DROP

# Save
iptables-save > /etc/iptables/rules.v4
```

### 10.3 Container Isolation

The production compose file enforces:

- **No host networking** — all containers use Docker bridge network
- **No privileged mode** — except GPU (required by NVIDIA runtime)
- **Read-only root filesystem** — API and frontend can't write to their filesystems
- **All capabilities dropped** — can't perform privileged operations
- **No-new-privileges** — can't escalate via setuid binaries
- **Memory limits** — prevent OOM on the host
- **Internal-only ports** — DBs and Ollama not accessible from outside

### 10.4 Secrets Management

**Option A: `.env` file (simple)**

```bash
chmod 600 .env
```

**Option B: Docker Secrets (Swarm)**

```bash
echo "your-password" | docker secret create db_password -
```

Reference in compose:

```yaml
services:
  api:
    secrets:
      - db_password
secrets:
  db_password:
    external: true
```

### 10.5 Changing Default Credentials

| Service | Default | How to Change |
|---------|---------|---------------|
| PostgreSQL | `shadowhive:shadowhive` | Set `POSTGRES_PASSWORD` in `.env` |
| Neo4j | `neo4j:shadowhive` | Set `NEO4J_PASSWORD` in `.env` |

Always change these **before** exposing the service to a network.

---

## 11. Storage & Backups

### 11.1 Named Volumes

| Volume | Service | Contains | Size (Typical) |
|--------|---------|----------|-----------------|
| `pgdata` | PostgreSQL | Generated companies, events, profiles | 100 MB - 2 GB |
| `neodata` | Neo4j | Graph relationships, attack paths | 50 MB - 1 GB |
| `ollamadata` | Ollama | Downloaded LLM models (~2 GB each) | 2 GB - 12 GB |
| `honeypot_data` | Cowrie + Portal | Deployed company artifacts (userdb.txt, filesystem contents, metadata) | 10 MB - 500 MB |

Locations on the host (Docker-managed):

```bash
/var/lib/docker/volumes/shadowhive_pgdata/_data
/var/lib/docker/volumes/shadowhive_neodata/_data
/var/lib/docker/volumes/shadowhive_ollamadata/_data
```

### 11.2 Backup Commands

```bash
# Full backup via Makefile
make backup BACKUP_DIR=/var/backups/shadowhive

# Or manually:

# PostgreSQL (best — SQL dump, portable)
docker compose exec -T postgres pg_dump -U shadowhive shadowhive \
  | gzip > /var/backups/shadowhive/pgdump-$(date +%Y%m%d).sql.gz

# Neo4j (full data directory)
docker run --rm -v shadowhive_neodata:/data -v /var/backups/shadowhive:/backup \
  alpine tar czf /backup/neo4j-$(date +%Y%m%d).tar.gz -C /data .

# Ollama models (large files — backup less frequently)
docker run --rm -v shadowhive_ollamadata:/data -v /var/backups/shadowhive:/backup \
  alpine tar czf /backup/ollama-$(date +%Y%m%d).tar.gz -C /data .
```

### 11.3 Cron Backup Script

Create `scripts/backup.sh`:

```bash
#!/bin/bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/shadowhive}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
COMPOSE_DIR="/opt/shadowhive"

mkdir -p "$BACKUP_DIR"
cd "$COMPOSE_DIR"

echo "[$(date)] Starting backup..."

# PostgreSQL
docker compose exec -T postgres pg_dump -U shadowhive shadowhive \
  | gzip > "$BACKUP_DIR/pgdump-$(date +%Y%m%d-%H%M%S).sql.gz"
echo "  PostgreSQL: done"

# Volumes
for vol in shadowhive_pgdata; do
  docker run --rm -v "${vol}":/source -v "${BACKUP_DIR}":/backup \
    alpine tar czf "/backup/vol-$(basename ${vol})-$(date +%Y%m%d-%H%M%S).tar.gz" \
    -C /source . 2>/dev/null
done
echo "  Volumes: done"

# Cleanup old backups
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +$RETENTION_DAYS -delete

echo "[$(date)] Backup complete"
```

Make it executable and add to crontab:

```bash
chmod +x scripts/backup.sh
echo "0 2 * * * /opt/shadowhive/scripts/backup.sh" | crontab -
```

### 11.4 Restore Procedure

```bash
# 1. Stop services that use the database
docker compose stop api

# 2. Restore PostgreSQL from SQL dump
gunzip -c /var/backups/shadowhive/pgdump-20240101-020000.sql.gz \
  | docker compose exec -T postgres psql -U shadowhive shadowhive

# 3. Restore a volume from tar
docker run --rm -v shadowhive_pgdata:/target -v /var/backups/shadowhive:/backup \
  alpine sh -c "rm -rf /target/* && tar xzf /backup/vol-pgdata-20240101-020000.tar.gz -C /target"

# 4. Restart services
docker compose up -d
```

---

## 12. Monitoring & Maintenance

### 12.1 Health Check Endpoints

| Service | Endpoint | Expected |
|---------|----------|----------|
| API | `http://localhost:8000/api/companies/health` | `200` |
| Frontend | `http://localhost:3000/` | `200` |
| Postgres | `pg_isready -U shadowhive` | `accepting connections` |
| Neo4j | `cypher-shell -u neo4j 'RETURN 1'` | `1` |

### 12.2 Log Access

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f api
docker compose logs -f ollama

# Last N lines
docker compose logs --tail=100 api

# Timestamps
docker compose logs -t -f
```

### 12.3 Updating the Stack

```bash
# Pull latest images
docker compose pull

# Rebuild and restart
docker compose up -d --build

# Or via Makefile
make update
```

After updating, verify:

```bash
make ps
# All services should be "Up" or "healthy"
```

### 12.4 Log Rotation

Docker's built-in log rotation:

```bash
# Configure in /etc/docker/daemon.json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}

# Or per-service in docker-compose.yml:
services:
  api:
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```

### 12.5 Resource Monitoring

```bash
# Live resource usage
docker stats

# Disk usage
docker system df

# Volume sizes
docker run --rm -v shadowhive_pgdata:/data alpine du -sh /data
```

---

## 13. Troubleshooting

### 13.1 Ollama Not Responding / Timeout

**Symptom:** Generation fails with `TimeoutError` or "Ollama not reachable"

**Causes & fixes:**

| Cause | Fix |
|-------|-----|
| Model not pulled | `docker compose exec ollama ollama pull llama3.2:3b` |
| Out of memory | Check RAM: `free -h`; switch to a smaller model |
| Ollama container not running | `docker compose logs ollama` |
| Timeout too short | Already set to 600s in config; check network latency |

**Verify Ollama is working:**

```bash
# Check container logs
docker compose logs ollama

# Test direct API call
curl -s http://localhost:11434/api/generate \
  -d '{"model":"llama3.2:3b","prompt":"Hello","stream":false}'
```

### 13.2 Database Connection Refused

**Symptom:** API logs show `psycopg2.OperationalError` or `connection refused`

**Causes & fixes:**

| Cause | Fix |
|-------|-----|
| Postgres container not healthy | `docker compose logs postgres` |
| Wrong password | Check `.env` matches `configs/default.yaml` |
| Port mismatch | Check `configs/default.yaml` database section |
| Postgres still starting | Wait 10-15s for first startup (creates initial DB) |

### 13.3 Frontend Can't Reach API

**Symptom:** UI shows "Network Error" or API calls return 404/502

**Causes & fixes:**

| Cause | Fix |
|-------|-----|
| API container not running | `docker compose ps api` |
| Wrong `NEXT_PUBLIC_API_URL` | In dev: `http://api:8000`; in prod: same as reverse proxy URL |
| CORS mismatch | API logs show CORS errors; update `configs/default.yaml` |
| nginx/Caddy not running | Check reverse proxy container status |

**Verify the proxy chain:**

```bash
# Direct API access
curl -s http://localhost:8000/api/companies/health

# Through proxy
curl -s http://localhost/api/companies/health
```

### 13.4 Generation Fails with Empty String Error

**Symptom:** Task status is "failed" with empty error message

**Cause:** The LLM returned empty or non-JSON content. This is often a
transient issue with Ollama (especially on low-RAM systems).

**Fixes:**

```bash
# 1. Check Ollama logs for errors
docker compose logs --tail=50 ollama

# 2. Check API logs for the JSON parse failure
docker compose logs --tail=50 api | grep -i "json\|parse\|warning"

# 3. Increase Ollama timeout in configs/default.yaml
#    (already 600s — increase further if needed)

# 4. Switch to a smaller model if RAM is low
#    In configs/default.yaml: change to llama3.2:1b

# 5. Try regenerating — often a transient issue
```

### 13.5 GPU Not Detected in Ollama

**Symptom:** `nvidia-smi` inside container returns "command not found" or no GPU

**Causes & fixes:**

| Cause | Fix |
|-------|-----|
| NVIDIA Container Toolkit not installed | Install per Section 8 |
| Missing `runtime: nvidia` in compose | Use `docker-compose.gpu.yml` |
| nvidia-docker runtime not configured | `sudo nvidia-ctk runtime configure --runtime=docker` |
| GPU driver not loaded | `lsmod | grep nvidia` |
| Wrong model | Some models may not use GPU well; check Ollama docs |

### 13.6 Out of Memory / Container OOM-Killed

**Symptom:** Container exits with code 137 or `docker compose ps` shows "Exit 137"

**Fix:**

```bash
# Check which container is OOM
docker compose logs --tail=50 ollama

# Free memory
docker compose down  # Stops everything
sudo sync && echo 3 | sudo tee /proc/sys/vm/drop_caches

# Reduce memory usage
# 1. Use smaller model (llama3.2:1b instead of 3b)
# 2. Limit Ollama to fewer threads:
#    In configs/default.yaml: ollama: base_url: http://ollama:11434
#    Set OLLAMA_NUM_THREADS=4 in docker-compose.yml environment
# 3. Reduce generation size (fewer employees, emails, docs)
```

### 13.7 Auth: "Invalid token signature"

**Symptom:** API returns `401 Invalid token signature` after login.

**Cause:** The `JWT_SECRET` is either empty (ephemeral) or changed between token issuance and verification. When `JWT_SECRET` is not set, a random key is generated per API process — restarting the container invalidates all tokens.

**Fix:** Set a persistent `JWT_SECRET` in `.env`:
```bash
JWT_SECRET=$(openssl rand -base64 32)
```

### 13.8 Auth: "Auth is disabled"

**Symptom:** Auth endpoints return `400 Auth is disabled`.

**Cause:** `AUTH_ENABLED` is set to `false`.

**Fix:** Set `AUTH_ENABLED=true` in `.env`, then recreate the API container:
```bash
docker compose up -d --force-recreate api
```

### 13.9 Account Locked Out

**Symptom:** API returns `429 Account locked` after failed login attempts.

**Cause:** 5 consecutive failed login attempts triggers a 15-minute lockout.

**Fix:** Wait 15 minutes, or unlock via database:
```bash
docker compose exec postgres psql -U shadowhive -d shadowhive \
  -c "UPDATE users SET failed_login_attempts = 0, locked_until = NULL WHERE email = 'user@example.com';"
```

### 13.10 Ingested Events Not Showing

**Symptom:** `POST /api/events` returns 200 but dashboard still shows 0 threats.

**Causes & fixes:**

| Cause | Fix |
|-------|-----|
| Wrong event format | Check Cowrie format: `eventid`, `src_ip`, `session`, `timestamp` required |
| Wrong `Content-Type` | Set `Content-Type: application/json` header |
| Events wrapped wrong | Must be `{"events": [...]}`, not a bare array |
| Auth token invalid | Include `Authorization: Bearer <token>` if auth is on |

**Test with a minimal event:**
```bash
curl -s -X POST "http://localhost:8000/api/events" \
  -H "Content-Type: application/json" \
  -d '{"events":[{"eventid":"cowrie.session.connect","src_ip":"10.0.0.1","session":"test-session","timestamp":"2026-06-12T12:00:00","message":"test"}]}'
```

### 13.10 Port Conflicts

**Symptom:** `docker compose up` fails with "port is already allocated"

**Causes & fixes:**

| Port | Typical Conflict | Fix |
|------|------------------|-----|
| 5432 | Local PostgreSQL | `sudo systemctl stop postgresql` or change host port |
| 8000 | Another FastAPI/Uvicorn instance | Change to `8001:8000` in compose |
| 3000 | Another Next.js instance | Change to `3001:3000` in compose |
| 11434 | Another Ollama instance | Stop other Ollama: `systemctl --user stop ollama` |

---

## 14. Reference

### 14.1 Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                         HOST (Docker)                                 │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────┐        │
│  │              Docker Bridge Network (172.x.x.x)            │        │
│  │                                                           │        │
│  │  ┌──────────┐    ┌──────────┐    ┌──────────┐            │        │
│  │  │  nginx   │    │  api     │    │ frontend  │            │        │
│  │  │  80/443  │───►│  :8000   │    │  :3000    │            │        │
│  │  └──────────┘    └────┬─────┘    └──────────┘            │        │
│  │                       │                                   │        │
│  │              ┌────────┼────────┐                          │        │
│  │              ▼        ▼        ▼                          │        │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐│        │
│  │  │ postgres │ │  neo4j   │ │  ollama  │ │  cowrie  │ │  portal  ││        │
│  │  │  :5432   │ │:7474/7687│ │  :11434  │ │  :2222   │ │  :8001   ││        │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘│        │
│  │                       │                                   │        │
│  │  ┌────────────────────┴────────────────────┐               │        │
│  │  │         HONEYPOT FARM (profile: full)     │               │        │
│  │  │                                          │               │        │
│  │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐│               │        │
│  │  │  │ opencanary│ │ dionaea  │ │ cowrie2  ││               │        │
│  │  │  │ :21,23,...│ │ :21,445..│ │ :2223    ││               │        │
│  │  │  └──────────┘ └──────────┘ └──────────┘│               │        │
│  │  │  ┌──────────┐ ┌──────────┐              │               │        │
│  │  │  │ cowrie3  │ │ wordpress│              │               │        │
│  │  │  │ :2224    │ │ :8081    │              │               │        │
│  │  │  └──────────┘ └──────────┘              │               │        │
│  │  └──────────────────────────────────────────┘               │        │
│  │                                                           │        │
│  └──────────────────────────────────────────────────────────┘        │
│                                                                       │
│  Volumes: pgdata  neodata  ollamadata  cowriedata[2,3]  dionaeadata │
│           honeypot_data                                              │
│  Bind mounts: honeypot_logs/ (shared across all honeypots + API)     │
└──────────────────────────────────────────────────────────────────────┘
```

### 14.2 File Tree of Deployment-Relevant Files

```
shadowhive/
├── DEPLOYMENT.md              ← You are here
├── docker-compose.yml          Base compose (dev defaults)
├── docker-compose.prod.yml     Production overrides (resources, security)
├── docker-compose.gpu.yml      GPU acceleration override
├── docker-compose.nginx.yml    nginx reverse proxy
├── docker-compose.caddy.yml    Caddy reverse proxy
├── Makefile                    Ops commands
├── .env.example                Environment template
├── .dockerignore               Build context filter
├── Dockerfile                  Two-stage backend Dockerfile
├── Caddyfile                   Caddy configuration
├── nginx/
│   ├── Dockerfile              nginx image
│   └── nginx.conf              Hardened nginx config
├── frontend/
│   └── Dockerfile              Two-stage frontend Dockerfile
├── configs/
│   └── default.yaml            All application configuration
├── portal/
│   ├── Dockerfile               FastAPI + Jinja2 portal image
│   ├── main.py                  Company website routes (vulnerable + decoy endpoints)
│   ├── requirements.txt         Python dependencies
│   ├── static/
│   │   ├── style.css            Responsive design with utility classes, animations & mobile breakpoints (zero inline styles in templates)
│   │   ├── favicon.svg          SVG favicon
│   │   ├── preview.html         Standalone preview file (open directly for CSS dev, no server needed)
│   └── templates/               Jinja2 HTML templates (8 pages, base layout, all CSS utility classes)
├── scripts/
│   ├── backup.sh               Backup script (create from Section 11)
│   ├── cowrie.cfg              Main Cowrie SSH honeypot config (JSON log engine)
│   └── honeypots/
│       ├── opencanary.json     OpenCanary 12-protocol config
│       ├── cowrie2.cfg         Second Cowrie instance config
│       └── cowrie3.cfg         Third Cowrie instance config
├── wordpress/
│   ├── Dockerfile              WordPress honeypot multi-stage build
│   ├── log_watcher.py          Apache access log → JSON honeypot events
│   ├── wp-config.php           Vulnerable WordPress config
│   └── index.html              Fake WordPress landing page
├── cowriedata/                 [Docker volume] Cowrie logs and data
├── cowriedata2/                [Docker volume] Cowrie2 logs and data
├── cowriedata3/                [Docker volume] Cowrie3 logs and data
├── dionaeadata/                [Docker volume] Dionaea logs and data
├── honeypot_logs/              [Host bind mount, shared] All honeypot JSON event logs
│   ├── opencanary.json         OpenCanary events
│   ├── portal_honeypot.json    Portal honeypot login captures
│   ├── cowrie2.json            Cowrie2 events
│   ├── cowrie3.json            Cowrie3 events
│   └── wordpress.json          WordPress honeypot events
└── honeypot_data/              [Docker volume, shared] Deploy artifacts
    ├── userdb.txt              Cowrie auth — employee credentials
    ├── contents/               Cowrie filesystem (home dirs, projects)
    └── active_company.json     Portal metadata
```

### 14.3 Quick Command Reference

```bash
# ========== Lifecycle ==========
make up                          # Dev mode
make PROFILE=prod up             # Production mode
make PROFILE=prod-gpu up         # Production + GPU
make down                        # Stop all
make restart                     # Restart all
make logs                        # Tail all logs
make ps                          # Show status

# ========== Build ==========
make build                       # Rebuild all
make build-api                   # Rebuild API only
make build-frontend              # Rebuild frontend only

# ========== Updates ==========
make update                      # Pull + rebuild + restart
make pull-model                  # Download LLM model

# ========== Backups ==========
make backup                      # Full backup
make restore BACKUP_NAME=...     # Restore from backup

# ========== Help ==========
make help                        # Show all commands

# ========== Docker Swarm ==========
docker stack deploy -c docker-stack.yml shadowhite
docker stack services shadowhive
docker service scale shadowhive_api=3
```

---

> **Last updated:** June 2026  
> **Questions?** Open an issue at https://github.com/your-org/shadowhive/issues  
> **Security concerns?** Email security@your-org.com
