import json
import logging
import os
import random
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("shadowhive")

HONEYPOT_DIR = os.environ.get("HONEYPOT_DATA_DIR", "/app/honeypot_data")

PASSWORD_POOLS = {
    "neglected": ["Welcome1!", "Password123", "admin123", "letmein", "Company2024!"],
    "startup": ["Welcome2024!", "Passw0rd!", "Changeme1", "Summer2024!"],
    "default": ["Welcome2024!", "Passw0rd!", "Changeme1", "Summer2024!"],
    "mature": ["C0rporate#Sec2024", "N3tw0rk!Admin2024", "P@ssw0rd!Sec"],
}


def _password_for(posture: str) -> str:
    return random.choice(PASSWORD_POOLS.get(posture, PASSWORD_POOLS["default"]))


def _build_userdb(employees, company_domain: str, posture: str) -> str:
    lines = []
    for emp in employees:
        pw = _password_for(posture)
        uid = random.randint(1001, 60000)
        home = f"/home/{emp.first_name.lower()}.{emp.last_name.lower()}"
        lines.append(f"{emp.email}:{pw}:{uid}:{uid}::{home}:/bin/bash")
    lines.append("root:toor:0:0::/root:/bin/bash")
    return "\n".join(lines) + "\n"


def _bash_history(user_name: str, company_slug: str) -> str:
    return "\n".join(
        [
            "whoami",
            "id",
            "hostname",
            "cat /etc/hostname",
            "uname -a",
            "cat /etc/os-release",
            "df -h",
            "free -m",
            "ps aux",
            "netstat -tlnp",
            "ip addr",
            f"ls -la /home/{user_name}/",
            f"cd /var/www/{company_slug}/",
            "ls -la",
            "tail -f /var/log/nginx/access.log",
            "cat /var/log/auth.log | tail -20",
            "cat /etc/nginx/sites-enabled/default",
            "systemctl status nginx",
            "cat /var/backups/db_dump.sql | grep -i admin",
            "ls -la /opt/internal/",
            "cat /opt/internal/config.yaml",
            "curl -s http://localhost/ | head -50",
            "exit",
            "",
        ]
    )


def _nginx_config(company_slug: str, portal_url: str) -> str:
    return f"""server {{
    listen 80;
    server_name {company_slug}.local www.{company_slug}.local;

    # Company portal
    location / {{
        proxy_pass {portal_url};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }}

    location /static/ {{
        alias /var/www/{company_slug}/static/;
    }}

    location /backup/ {{
        alias /var/backups/;
        autoindex on;
    }}
}}
"""


def _db_dump(company_name: str, employees) -> str:
    lines = [
        f"-- PostgreSQL database dump for {company_name}",
        f"-- Generated: {datetime.now(UTC).isoformat()}",
        "",
        "CREATE TABLE employees (",
        "    id UUID PRIMARY KEY,",
        "    first_name VARCHAR(100),",
        "    last_name VARCHAR(100),",
        "    email VARCHAR(255),",
        "    title VARCHAR(255),",
        "    department VARCHAR(255),",
        "    salary INTEGER",
        ");",
        "",
        "INSERT INTO employees (id, first_name, last_name, email, title, department, salary) VALUES",
    ]
    emp_rows = []
    for i, emp in enumerate(employees):
        emp_rows.append(
            f"    ('{uuid.uuid4()}', '{emp.first_name}', '{emp.last_name}', "
            f"'{emp.email}', '{emp.title}', '{emp.department}', "
            f"{random.randint(60000, 200000)})"
        )
    lines.append(",\n".join(emp_rows) + ";")
    lines.extend(
        [
            "",
            "CREATE TABLE credentials (",
            "    id UUID PRIMARY KEY,",
            "    service VARCHAR(255),",
            "    username VARCHAR(255),",
            "    password VARCHAR(255)",
            ");",
            "",
            "INSERT INTO credentials VALUES",
            f"    ('{uuid.uuid4()}', 'postgresql', 'admin', '{_password_for('default')}'),",
            f"    ('{uuid.uuid4()}', 'redis', 'default', '{_password_for('default')}'),",
            f"    ('{uuid.uuid4()}', 'api', 'svc_token', 'sk-{uuid.uuid4().hex[:24]}');",
        ]
    )
    return "\n".join(lines)


def _auth_log() -> str:
    now = datetime.now(UTC)
    entries = []
    for i in range(random.randint(5, 15)):
        ts = now.replace(hour=random.randint(0, 23), minute=random.randint(0, 59), second=random.randint(0, 59))
        ip = f"{random.randint(10, 223)}.{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}"
        user = random.choice(["root", "admin", "ubuntu", "deploy"])
        entries.append(
            f"{ts.strftime('%b %d %H:%M:%S')} sshd[12345]: Failed password for {user} from {ip} port 22 ssh2"
        )
    entries.append(
        f"{now.strftime('%b %d %H:%M:%S')} sshd[12345]: Accepted password for root from 10.0.0.1 port 22 ssh2"
    )
    return "\n".join(entries) + "\n"


def _internal_config(company_name: str, employees, posture: str) -> str:
    slack_webhook = f"https://hooks.slack.com/services/T{''.join(random.choices('0123456789ABCDEF', k=8))}/B{''.join(random.choices('0123456789ABCDEF', k=8))}/{''.join(random.choices('0123456789abcdef', k=24))}"
    cfg = {
        "company": company_name,
        "environment": "production",
        "monitoring": {
            "slack_webhook": slack_webhook,
            "pagerduty_key": f"pd-{uuid.uuid4().hex[:16]}",
        },
        "database": {
            "host": "postgres.internal",
            "port": 5432,
            "name": "company_db",
            "user": "app_user",
            "password": _password_for(posture),
        },
        "redis": {
            "host": "redis.internal",
            "port": 6379,
            "password": _password_for(posture),
        },
        "api_keys": {},
    }
    for emp in random.sample(list(employees), min(2, len(employees))):
        cfg["api_keys"][emp.email] = f"sk-{uuid.uuid4().hex[:24]}"
    return json.dumps(cfg, indent=2)


def _employee_notes(emp, company_name: str) -> str:
    templates = [
        f"TODO: Review {emp.department} Q{random.randint(1, 4)} budget allocation\n- Server infrastructure: ${random.randint(10000, 100000)}\n- Software licenses: ${random.randint(5000, 50000)}\n- Contractor fees: ${random.randint(10000, 80000)}",
        f"Meeting notes — {company_name} {emp.department} standup\n\nAttendees: team leads\n\n- Migration to cloud 80% complete\n- Pending security review for new API endpoints\n- Updated access controls for {random.choice(['finance', 'hr', 'engineering', 'admin'])} systems",
        f"Onboarding checklist — new hire\n\n1. Create accounts (AD, LDAP, email)\n2. Set up workstation\n3. Assign to {emp.department} team\n4. Schedule security awareness training\n5. Issue YubiKey\n6. Document signing (NDA)",
    ]
    return random.choice(templates)


def _write_contents(contents_dir: str, company, employees, posture: str):
    slug = company.name.lower().replace(" ", "").replace("'", "").replace("-", "")[:32]
    os.makedirs(contents_dir, exist_ok=True)

    etc_dir = os.path.join(contents_dir, "etc", "nginx", "sites-enabled")
    os.makedirs(etc_dir, exist_ok=True)
    with open(os.path.join(contents_dir, "etc", "hostname"), "w") as f:
        f.write(f"{slug}-srv-01\n")
    with open(os.path.join(contents_dir, "etc", "resolv.conf"), "w") as f:
        f.write("nameserver 8.8.8.8\nnameserver 1.1.1.1\n")
    with open(os.path.join(etc_dir, "default"), "w") as f:
        f.write(_nginx_config(slug, "http://portal:8001"))

    var_backups = os.path.join(contents_dir, "var", "backups")
    os.makedirs(var_backups, exist_ok=True)
    with open(os.path.join(var_backups, "db_dump.sql"), "w") as f:
        f.write(_db_dump(company.name, employees))

    var_log = os.path.join(contents_dir, "var", "log")
    os.makedirs(var_log, exist_ok=True)
    with open(os.path.join(var_log, "auth.log"), "w") as f:
        f.write(_auth_log())

    var_www = os.path.join(contents_dir, "var", "www", slug)
    os.makedirs(var_www, exist_ok=True)
    with open(os.path.join(var_www, "index.html"), "w") as f:
        f.write(
            f"<html><body><h1>{company.name} — Internal Web Server</h1><p>Welcome to the internal corporate portal.</p></body></html>\n"
        )

    opt_dir = os.path.join(contents_dir, "opt", "internal")
    os.makedirs(opt_dir, exist_ok=True)
    with open(os.path.join(opt_dir, "config.yaml"), "w") as f:
        f.write(_internal_config(company.name, employees, posture))

    tmp_dir = os.path.join(contents_dir, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    with open(os.path.join(tmp_dir, "credentials.txt"), "w") as f:
        f.write(f"# DO NOT COMMIT — internal notes\n# {company.name} service credentials\n\n")
        for emp in random.sample(list(employees), min(2, len(employees))):
            f.write(f"{emp.email}:{_password_for(posture)}\n")

    for emp in employees:
        user = f"{emp.first_name.lower()}.{emp.last_name.lower()}"
        home_dir = os.path.join(contents_dir, "home", user)
        os.makedirs(os.path.join(home_dir, ".ssh"), exist_ok=True)
        os.makedirs(os.path.join(home_dir, "documents"), exist_ok=True)

        with open(os.path.join(home_dir, ".bash_history"), "w") as f:
            f.write(_bash_history(user, slug))
        with open(os.path.join(home_dir, ".ssh", "id_rsa.pub"), "w") as f:
            f.write(
                f"ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789', k=100))} {emp.email}\n"
            )
        with open(os.path.join(home_dir, "documents", "notes.txt"), "w") as f:
            f.write(_employee_notes(emp, company.name))

    logger.info(f"Wrote Cowrie filesystem contents ({len(employees)} users) to {contents_dir}")


async def deploy_company(db: AsyncSession, company_id: uuid.UUID) -> dict:
    from backend.models.company import Company, Employee

    company = await db.get(Company, company_id)
    if not company:
        raise ValueError(f"Company {company_id} not found")

    employees = (await db.execute(select(Employee).where(Employee.company_id == company_id))).scalars().all()

    posture = "default"
    if company.extra_data and isinstance(company.extra_data, dict):
        posture = company.extra_data.get("security_posture", "default")

    base_dir = HONEYPOT_DIR
    os.makedirs(base_dir, exist_ok=True)

    userdb = _build_userdb(employees, company.name, posture)
    with open(os.path.join(base_dir, "userdb.txt"), "w") as f:
        f.write(userdb)

    contents_dir = os.path.join(base_dir, "contents")
    _write_contents(contents_dir, company, employees, posture)

    marker = {
        "company_id": str(company_id),
        "company_name": company.name,
        "deployed_at": datetime.now(UTC).isoformat(),
        "employee_count": len(employees),
    }
    with open(os.path.join(base_dir, "active_company.json"), "w") as f:
        json.dump(marker, f)

    logger.info(f"Deployed company {company.name} ({company_id}) to honeypot directory")

    restart_ok = await _restart_cowrie()
    marker["cowrie_restarted"] = restart_ok

    return marker


async def undeploy_company() -> dict:
    base_dir = HONEYPOT_DIR
    marker_path = os.path.join(base_dir, "active_company.json")

    if os.path.exists(marker_path):
        with open(marker_path) as f:
            prev = json.load(f)
        os.remove(marker_path)

    userdb_path = os.path.join(base_dir, "userdb.txt")
    if os.path.exists(userdb_path):
        os.remove(userdb_path)

    import shutil

    contents_dir = os.path.join(base_dir, "contents")
    if os.path.exists(contents_dir):
        shutil.rmtree(contents_dir)

    await _restart_cowrie()
    return {"undeployed": True, "previous": prev.get("company_name") if prev else None}


async def get_deployment_status() -> dict:
    base_dir = HONEYPOT_DIR
    marker_path = os.path.join(base_dir, "active_company.json")
    if not os.path.exists(marker_path):
        return {"active": False, "company_id": None, "company_name": None}
    with open(marker_path) as f:
        return {"active": True, **json.load(f)}


async def _restart_cowrie() -> bool:
    socket_path = "/var/run/docker.sock"
    if not os.path.exists(socket_path):
        logger.info("Docker socket not available — Cowrie restart required manually")
        return False
    try:
        import httpx

        transport = httpx.AsyncHTTPTransport(uds=socket_path)
        async with httpx.AsyncClient(transport=transport) as client:
            resp = await client.post(
                "http://localhost/v1.47/containers/shadowhive-cowrie-1/restart",
            )
            if resp.status_code == 204:
                logger.info("Cowrie restarted successfully via Docker API")
                return True
            logger.warning(f"Cowrie restart failed via API: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        logger.warning(f"Cowrie restart error: {e}")
        return False
