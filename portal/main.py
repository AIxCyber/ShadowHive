import json
import os
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import create_engine, text

HONEYPOT_DIR = os.environ.get("HONEYPOT_DATA_DIR", "/app/honeypot_data")
HONEYPOT_LOG_DIR = os.environ.get("HONEYPOT_LOG_DIR", "/app/honeypot_logs")
DB_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "shadowhive")
DB_URL = f"postgresql://shadowhive:{DB_PASSWORD}@postgres:5432/shadowhive"

templates = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"))

app = FastAPI(title="Company Portal", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


def _log_honeypot_event(event_type: str, source_ip: str, path: str, data: dict | None = None):
    """Write a credential harvest event to the shared JSON log for ShadowHive ingestion."""
    log_dir = Path(HONEYPOT_LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "portal_honeypot.json"
    event = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event_type": event_type,
        "source_ip": source_ip,
        "path": path,
        "remote_addr": source_ip,
    }
    if data:
        event["data"] = {k: v for k, v in data.items() if k in ("username", "password", "email", "api_key")}
    with open(log_file, "a") as f:
        f.write(json.dumps(event) + "\n")


def get_active_company() -> dict | None:
    marker = Path(HONEYPOT_DIR) / "active_company.json"
    if not marker.exists():
        return None
    try:
        return json.loads(marker.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def query_company(company_id: str) -> dict | None:
    engine = create_engine(DB_URL)
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT id, name, industry, size, description, location_city, location_country, founded_year, org_chart, extra_data, created_at FROM companies WHERE id = :id"),
                {"id": company_id},
            ).fetchone()
            if not row:
                return None
            company = dict(row._mapping)

            employees = conn.execute(
                text("SELECT id, first_name, last_name, email, title, department, bio FROM employees WHERE company_id = :cid ORDER BY department, last_name"),
                {"cid": company_id},
            ).fetchall()
            company["employees"] = [dict(r._mapping) for r in employees]

            emails = conn.execute(
                text("SELECT id, sender_id, recipient_ids, subject, body, sent_at FROM emails WHERE company_id = :cid ORDER BY sent_at LIMIT 20"),
                {"cid": company_id},
            ).fetchall()
            emails_data = [dict(r._mapping) for r in emails]
            for e in emails_data:
                if isinstance(e.get("sent_at"), datetime):
                    e["sent_at"] = e["sent_at"].strftime("%Y-%m-%d")
            company["emails"] = emails_data

            documents = conn.execute(
                text("SELECT id, title, doc_type, content FROM documents WHERE company_id = :cid"),
                {"cid": company_id},
            ).fetchall()
            company["documents"] = [dict(r._mapping) for r in documents]

            return company
    finally:
        engine.dispose()


def _job_listings(company: dict) -> list[dict]:
    """Generate realistic job listings from company data."""
    import random
    depts = []
    if company.get("org_chart"):
        depts = [d["name"] for d in company["org_chart"]]
    if not depts:
        depts = [f"{company.get('industry', 'Engineering')} Engineering", "Product", "Operations"]

    titles_pool = [
        ("Senior", "Lead", ["$120k", "$160k", "$180k", "$200k", "$250k"]),
        ("Staff", "Architect", ["$150k", "$180k", "$220k", "$280k"]),
        ("", "Associate", ["$65k", "$75k", "$85k", "$95k", "$110k"]),
        ("Principal", "Manager", ["$130k", "$160k", "$190k", "$230k"]),
    ]
    jobs = []
    used = set()
    for dept in depts:
        for level, role, salaries in titles_pool:
            title = f"{level} {dept} {role}" if level else f"{dept} {role}"
            if title in used:
                continue
            used.add(title)
            salary = f"{random.choice(salaries)} – {random.choice(salaries)}"
            jobs.append({
                "title": title,
                "type": random.choice(["Full-time", "Full-time", "Contract"]),
                "location": company.get("location_city") or "Remote",
                "salary": salary,
                "department": dept,
            })
    return jobs[:8]


def render(template_name: str, **kwargs) -> str:
    import random
    active = get_active_company()
    ctx = {"active": active, "company": None, "now": datetime.now(UTC), **kwargs}
    if active and active.get("company_id"):
        ctx["company"] = query_company(active["company_id"])
    if ctx.get("company"):
        ctx["jobs"] = _job_listings(ctx["company"])
        ctx["phone"] = f"+1 (555) {random.randint(100, 999)}-{random.randint(1000, 9999)}"
    tmpl = templates.get_template(template_name)
    return tmpl.render(**ctx)


@app.get("/", response_class=HTMLResponse)
async def homepage():
    return render("index.html")


@app.get("/about", response_class=HTMLResponse)
async def about():
    return render("about.html")


@app.get("/team", response_class=HTMLResponse)
async def team():
    return render("team.html")


@app.get("/careers", response_class=HTMLResponse)
async def careers():
    return render("careers.html")


@app.get("/blog", response_class=HTMLResponse)
async def blog():
    return render("blog.html")


@app.api_route("/contact", methods=["GET", "POST"], response_class=HTMLResponse)
async def contact(request: Request):
    if request.method == "POST":
        form = await request.form()
        client_ip = request.client.host if request.client else "unknown"
        forwarded = request.headers.get("X-Forwarded-For", "")
        source_ip = forwarded.split(",")[0].strip() or client_ip
        _log_honeypot_event("web.contact_form", source_ip, "/contact", dict(form))
    return render("contact.html")


@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request):
    auth_header = request.headers.get("Authorization", "")
    authed = False
    if auth_header.startswith("Basic "):
        import base64
        decoded = base64.b64decode(auth_header.removeprefix("Basic ")).decode()
        admin_pw = os.environ.get("PORTAL_ADMIN_PASSWORD", "shadowhive2024")
        if decoded == f"admin:{admin_pw}":
            authed = True
    return render("admin.html", authed=authed)


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots():
    return """User-agent: *
Disallow: /admin
Disallow: /backup

Sitemap: https://example.com/sitemap.xml
"""


@app.get("/sitemap.xml", response_class=PlainTextResponse)
async def sitemap():
    active = get_active_company()
    name = ((active or {}).get("company_name", "example") or "example").lower().replace(" ", "")[:20] + ".com"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://{name}/</loc><priority>1.0</priority></url>
  <url><loc>https://{name}/about</loc><priority>0.8</priority></url>
  <url><loc>https://{name}/team</loc><priority>0.7</priority></url>
  <url><loc>https://{name}/careers</loc><priority>0.6</priority></url>
  <url><loc>https://{name}/blog</loc><priority>0.6</priority></url>
  <url><loc>https://{name}/contact</loc><priority>0.5</priority></url>
  <url><loc>https://{name}/admin</loc><priority>0.3</priority></url>
</urlset>"""


@app.get("/favicon.ico", response_class=PlainTextResponse)
async def favicon():
    return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="6" fill="#1a1a2e"/>
  <text x="16" y="22" text-anchor="middle" fill="#e94560" font-family="Arial" font-weight="bold" font-size="18">S</text>
</svg>"""


@app.get("/.env", response_class=PlainTextResponse)
async def env_file():
    import random
    active = get_active_company()
    name = (active or {}).get("company_name", "Company")
    slug = name.lower().replace(" ", "").replace("'", "")[:32]
    aws_id = "AKIA" + "".join(random.choices("0123456789ABCDEF", k=16))
    aws_secret = "".join(random.choices("0123456789abcdef", k=40))
    slack_id = "T" + "".join(random.choices("0123456789ABCDEFGHIJ", k=8))
    slack_channel = "C" + "".join(random.choices("0123456789ABCDEFGHIJ", k=8))
    slack_token = "xoxb-" + "-".join("".join(random.choices("0123456789abcdefghijklmnopqrstuvwxyz", k=n)) for n in [12, 16, 24])
    webhook_path = "/".join(
        random.choices([
            "services", "hooks", "webhooks", "integrations", "incoming",
        ], k=1)
        + [slack_id, slack_channel, "".join(random.choices("0123456789abcdefghijklmnopqrstuvwxyz", k=32))]
    )
    api_key = "sk-proj-" + uuid.uuid4().hex[:24]
    return f"""# {name} — Environment Configuration
APP_ENV=production
APP_DEBUG=false
DB_HOST=postgres.internal
DB_PORT=5432
DB_NAME={slug}_prod
DB_USER={slug[:12]}_app
DB_PASSWORD={''.join(random.choices('abcdefghijklmnopqrstuvwxyz', k=4))}{random.randint(10, 99)}!!"
REDIS_HOST=redis.internal
REDIS_PASSWORD={''.join(random.choices('abcdefghijklmnopqrstuvwxyz', k=6))}_{random.randint(1000, 9999)}
AWS_ACCESS_KEY_ID={aws_id}
AWS_SECRET_ACCESS_KEY={aws_secret}
SLACK_WEBHOOK=https://hooks.slack.com/{webhook_path}
SLACK_BOT_TOKEN={slack_token}
INTERNAL_API_KEY={api_key}
SENTRY_DSN=https://{uuid.uuid4().hex[:16]}@o{random.randint(100000, 999999)}.ingest.us.sentry.io/{random.randint(1000000, 9999999)}
"""


@app.get("/.htaccess", response_class=PlainTextResponse)
async def htaccess():
    return r"""# Apache configuration
<FilesMatch "\.(env|config|json|lock)$">
  Require all denied
</FilesMatch>

# Block bad bots
RewriteEngine On
RewriteCond %{HTTP_USER_AGENT} (bot|crawler|spider|scraper) [NC]
RewriteRule .* - [F,L]

# Protect config
<FilesMatch "config\.">
  Require all denied
</FilesMatch>

# Legacy API redirect — kept for backward compatibility
Redirect 301 /api/v1/old-endpoint /api/v2/new-endpoint
"""


@app.get("/.git/config", response_class=PlainTextResponse)
async def git_config():
    active = get_active_company()
    name = (active or {}).get("company_name", "company").lower().replace(" ", "-").replace("'", "")[:20]
    import random
    token = "ghp_" + "".join(random.choices("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=36))
    return f"""[core]
\trepositoryformatversion = 0
\tfilemode = true
\tbare = false
\tlogallrefupdates = true
[remote "origin"]
\turl = https://{token}@github.com/{name}/portal.git
\tfetch = +refs/heads/*:refs/remotes/origin/*
[branch "main"]
\tremote = origin
\tmerge = refs/heads/main
[user]
\tname = admin
\temail = devops@{name}.com
"""


@app.get("/composer.json", response_class=PlainTextResponse)
async def composer():
    return """{
  "name": "company/portal",
  "description": "Company Portal",
  "require": {
    "php": ">=8.1",
    "laravel/framework": "^10.0",
    "laravel/tinker": "^2.8",
    "spatie/laravel-permission": "^5.10"
  },
  "require-dev": {
    "fakerphp/faker": "^1.23",
    "mockery/mockery": "^1.6"
  },
  "config": {
    "optimize-autoloader": true
  }
}
"""


@app.get("/backup/", response_class=HTMLResponse)
async def backup_listing():
    active = get_active_company()
    name = (active or {}).get("company_name", "Company")
    slug = name.lower().replace(" ", "").replace("'", "")[:32]
    return f"""<!DOCTYPE html><html><body>
<h1>Index of /backup</h1><hr><pre>
<a href="../">../</a>
<a href="db_dump_2024-01-15.sql">db_dump_2024-01-15.sql</a>            2.3M
<a href="db_dump_2024-06-01.sql">db_dump_2024-06-01.sql</a>            2.5M
<a href="db_dump_2025-01-01.sql">db_dump_2025-01-01.sql</a>            2.8M
<a href="nginx_configs.tar.gz">nginx_configs.tar.gz</a>              45K
<a href="ssl_certs.tar.gz">ssl_certs.tar.gz</a>                  12K
</pre><hr><address>{slug} internal server</address></body></html>"""


HONEYPOT_LOGIN_PAGES = {
    "wp-login.php": ("WordPress Administration", "log", "pwd", "web.wp_login"),
    "phpmyadmin": ("phpMyAdmin", "pma_username", "pma_password", "web.phpmyadmin"),
    "jenkins": ("Jenkins CI/CD", "j_username", "j_password", "web.jenkins_login"),
    "gitlab": ("GitLab Enterprise", "username", "password", "web.gitlab_login"),
    "webmail": ("Corporate Webmail", "email", "password", "web.webmail_login"),
    "vpn": ("VPN Gateway Portal", "username", "password", "web.vpn_login"),
}


def _serve_login_page(title: str, user_field: str, pass_field: str, action: str, extra: str = "") -> str:
    return f"""<!DOCTYPE html><html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f0f2f5;display:flex;align-items:center;justify-content:center;min-height:100vh}}
form{{background:#fff;padding:40px;border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,.1);width:360px}}
h1{{font-size:1.5rem;margin-bottom:24px;color:#1a1a2e;text-align:center}}
label{{display:block;margin-bottom:6px;font-size:.85rem;color:#555}}
input[type=text],input[type=password],input[type=email]{{width:100%;padding:10px 12px;margin-bottom:16px;border:1px solid #ddd;border-radius:4px;font-size:.95rem;outline:none;transition:border-color .2s}}
input:focus{{border-color:#e94560}}
button{{width:100%;padding:12px;background:#e94560;color:#fff;border:none;border-radius:4px;font-size:1rem;cursor:pointer}}
button:hover{{background:#d63851}}
.error{{background:#fff3cd;color:#856404;padding:12px;border-radius:4px;margin-bottom:16px;font-size:.85rem;text-align:center}}
.footer{{margin-top:16px;font-size:.75rem;color:#999;text-align:center}}
{extra}
</style></head><body>
<form method="post" action="{action}">
<h1>{title}</h1>
<div class="error" style="display:none" id="error-msg">Invalid credentials. Please try again.</div>
<label>{user_field.replace('_', ' ').title()}</label>
<input type="text" name="{user_field}" autocomplete="off" required>
<label>Password</label>
<input type="password" name="{pass_field}" autocomplete="off" required>
<button type="submit">Sign In</button>
<div class="footer">Unauthorized access is prohibited.</div>
</form>
</body></html>"""


async def _handle_honeypot_login(request: Request, event_type: str, path: str):
    form = await request.form()
    creds = {k: v for k, v in form.items() if k in ("username", "password", "email", "log", "pwd", "pma_username", "pma_password", "j_username", "j_password", "api_key")}
    client_ip = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("X-Forwarded-For", "")
    source_ip = forwarded.split(",")[0].strip() or client_ip
    _log_honeypot_event(event_type, source_ip, path, creds)
    return HTMLResponse(
        _serve_login_page(
            title="WordPress Administration",
            user_field="log",
            pass_field="pwd",
            action="/wp-login.php",
            extra=".error{display:block!important}",
        ),
        status_code=200,
    )


@app.api_route("/wp-login.php", methods=["GET", "POST"], response_class=HTMLResponse)
async def wp_login(request: Request):
    if request.method == "POST":
        return await _handle_honeypot_login(request, "web.wp_login", "/wp-login.php")
    return HTMLResponse(_serve_login_page("WordPress Administration", "log", "pwd", "/wp-login.php"))


@app.api_route("/phpmyadmin/", methods=["GET", "POST"], response_class=HTMLResponse)
async def phpmyadmin(request: Request):
    if request.method == "POST":
        return await _handle_honeypot_login(request, "web.phpmyadmin", "/phpmyadmin/")
    return HTMLResponse(_serve_login_page("phpMyAdmin", "pma_username", "pma_password", "/phpmyadmin/"))


@app.api_route("/jenkins/", methods=["GET", "POST"], response_class=HTMLResponse)
async def jenkins_login(request: Request):
    if request.method == "POST":
        return await _handle_honeypot_login(request, "web.jenkins_login", "/jenkins/")
    return HTMLResponse(_serve_login_page("Jenkins CI/CD", "j_username", "j_password", "/jenkins/"))


@app.api_route("/gitlab/", methods=["GET", "POST"], response_class=HTMLResponse)
async def gitlab_login(request: Request):
    if request.method == "POST":
        return await _handle_honeypot_login(request, "web.gitlab_login", "/gitlab/")
    return HTMLResponse(_serve_login_page("GitLab Enterprise", "username", "password", "/gitlab/"))


@app.api_route("/webmail/", methods=["GET", "POST"], response_class=HTMLResponse)
async def webmail(request: Request):
    if request.method == "POST":
        return await _handle_honeypot_login(request, "web.webmail_login", "/webmail/")
    return HTMLResponse(_serve_login_page("Corporate Webmail", "email", "password", "/webmail/"))


@app.api_route("/vpn/", methods=["GET", "POST"], response_class=HTMLResponse)
async def vpn_login(request: Request):
    if request.method == "POST":
        return await _handle_honeypot_login(request, "web.vpn_login", "/vpn/")
    return HTMLResponse(_serve_login_page("VPN Gateway Portal", "username", "password", "/vpn/"))


@app.post("/api/v1/keys", response_class=PlainTextResponse)
async def api_key_harvest(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    client_ip = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("X-Forwarded-For", "")
    source_ip = forwarded.split(",")[0].strip() or client_ip
    _log_honeypot_event("web.api_key_harvest", source_ip, "/api/v1/keys", body)
    return PlainTextResponse("""{"error":"unauthorized","code":"API_KEY_INVALID"}""", status_code=401, media_type="application/json")
