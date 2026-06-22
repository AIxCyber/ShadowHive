import json

from backend.ai import get_provider_for_module
from backend.utils.config import Config
from backend.utils.json_parser import extract_json

MITRE_PROMPT = """You are a MITRE ATT&CK mapping system for cybersecurity threat intelligence.

Analyze this attacker event and map it to MITRE ATT&CK techniques.

Event type: {event_type}
Command: {command}
Raw data: {raw_data}

Return a JSON object with:
- technique_id: MITRE ATT&CK technique ID (e.g., T1059.001) or null if no match
- technique_name: human-readable technique name or null
- tactic: MITRE ATT&CK tactic (e.g., "execution") or null
- confidence: integer 1-100
- reasoning: one sentence explaining the mapping

ONLY return valid JSON, no other text."""


MITRE_TECHNIQUES = {
    "T1059.001": {"name": "Command and Scripting Interpreter: PowerShell", "tactic": "execution"},
    "T1059.004": {"name": "Command and Scripting Interpreter: Unix Shell", "tactic": "execution"},
    "T1003": {"name": "OS Credential Dumping", "tactic": "credential-access"},
    "T1046": {"name": "Network Service Discovery", "tactic": "discovery"},
    "T1082": {"name": "System Information Discovery", "tactic": "discovery"},
    "T1083": {"name": "File and Directory Discovery", "tactic": "discovery"},
    "T1070.004": {"name": "Indicator Removal: File Deletion", "tactic": "defense-evasion"},
    "T1048": {"name": "Exfiltration Over Alternative Protocol", "tactic": "exfiltration"},
    "T1190": {"name": "Exploit Public-Facing Application", "tactic": "initial-access"},
    "T1071.001": {"name": "Application Layer Protocol: Web Protocols", "tactic": "command-and-control"},
    "T1568": {"name": "Dynamic Resolution", "tactic": "command-and-control"},
    "T1574": {"name": "Hijack Execution Flow", "tactic": "persistence"},
    "T1036": {"name": "Masquerading", "tactic": "defense-evasion"},
    "T1055": {"name": "Process Injection", "tactic": "defense-evasion"},
    "T1505.003": {"name": "Web Shell", "tactic": "persistence"},
    "T1090": {"name": "Proxy", "tactic": "command-and-control"},
    "T1560": {"name": "Archive Collected Data", "tactic": "collection"},
    "T1110": {"name": "Brute Force", "tactic": "credential-access"},
    "T1021": {"name": "Remote Services", "tactic": "lateral-movement"},
    "T1552.001": {"name": "Unsecured Credentials: Credentials In Files", "tactic": "credential-access"},
}


def _pct(v: int) -> float:
    return v / 100.0


EVENT_TYPE_RULES: dict[str, dict] = {
    "cowrie.session.connect": {
        "technique_id": "T1021",
        "technique_name": "Remote Services",
        "tactic": "lateral-movement",
        "confidence": _pct(60),
    },
    "cowrie.session.closed": {
        "technique_id": "T1046",
        "technique_name": "Network Service Discovery",
        "tactic": "discovery",
        "confidence": _pct(40),
    },
    "cowrie.login.failed": {
        "technique_id": "T1110",
        "technique_name": "Brute Force",
        "tactic": "credential-access",
        "confidence": _pct(85),
    },
    "cowrie.login.success": {
        "technique_id": "T1078",
        "technique_name": "Valid Accounts",
        "tactic": "defense-evasion",
        "confidence": _pct(70),
    },
    "cowrie.client.version": {
        "technique_id": "T1046",
        "technique_name": "Network Service Discovery",
        "tactic": "discovery",
        "confidence": _pct(65),
    },
    "cowrie.client.kex": {
        "technique_id": "T1046",
        "technique_name": "Network Service Discovery",
        "tactic": "discovery",
        "confidence": _pct(50),
    },
    "cowrie.client.var": {
        "technique_id": "T1082",
        "technique_name": "System Information Discovery",
        "tactic": "discovery",
        "confidence": _pct(55),
    },
    "cowrie.session.params": {
        "technique_id": "T1082",
        "technique_name": "System Information Discovery",
        "tactic": "discovery",
        "confidence": _pct(45),
    },
    "cowrie.log.closed": {
        "technique_id": "T1070.004",
        "technique_name": "Indicator Removal: File Deletion",
        "tactic": "defense-evasion",
        "confidence": _pct(50),
    },
    "cowrie.client.size": {
        "technique_id": "T1082",
        "technique_name": "System Information Discovery",
        "tactic": "discovery",
        "confidence": _pct(30),
    },
    # ── OpenCanary event types ──────────────────────────────────────────
    "opencanary.ftp.login": {
        "technique_id": "T1110",
        "technique_name": "Brute Force",
        "tactic": "credential-access",
        "confidence": _pct(75),
    },
    "opencanary.telnet.login": {
        "technique_id": "T1110",
        "technique_name": "Brute Force",
        "tactic": "credential-access",
        "confidence": _pct(70),
    },
    "opencanary.smtp.login": {
        "technique_id": "T1110",
        "technique_name": "Brute Force",
        "tactic": "credential-access",
        "confidence": _pct(60),
    },
    "opencanary.pop3.login": {
        "technique_id": "T1110",
        "technique_name": "Brute Force",
        "tactic": "credential-access",
        "confidence": _pct(60),
    },
    "opencanary.imap.login": {
        "technique_id": "T1110",
        "technique_name": "Brute Force",
        "tactic": "credential-access",
        "confidence": _pct(60),
    },
    "opencanary.smb.access": {
        "technique_id": "T1021",
        "technique_name": "Remote Services",
        "tactic": "lateral-movement",
        "confidence": _pct(70),
    },
    "opencanary.mysql.login": {
        "technique_id": "T1110",
        "technique_name": "Brute Force",
        "tactic": "credential-access",
        "confidence": _pct(65),
    },
    "opencanary.rdp.login": {
        "technique_id": "T1021",
        "technique_name": "Remote Services",
        "tactic": "lateral-movement",
        "confidence": _pct(80),
    },
    "opencanary.vnc.login": {
        "technique_id": "T1021",
        "technique_name": "Remote Services",
        "tactic": "lateral-movement",
        "confidence": _pct(75),
    },
    "opencanary.http.request": {
        "technique_id": "T1190",
        "technique_name": "Exploit Public-Facing Application",
        "tactic": "initial-access",
        "confidence": _pct(50),
    },
    "opencanary.sip.call": {
        "technique_id": "T1071.001",
        "technique_name": "Application Layer Protocol: Web Protocols",
        "tactic": "command-and-control",
        "confidence": _pct(40),
    },
    "opencanary.tftp.request": {
        "technique_id": "T1048",
        "technique_name": "Exfiltration Over Alternative Protocol",
        "tactic": "exfiltration",
        "confidence": _pct(45),
    },
    "opencanary.git.clone": {
        "technique_id": "T1552.001",
        "technique_name": "Unsecured Credentials: Credentials In Files",
        "tactic": "credential-access",
        "confidence": _pct(55),
    },
    # ── Portal / web honeypot event types ───────────────────────────────
    "web.wp_login": {
        "technique_id": "T1078",
        "technique_name": "Valid Accounts",
        "tactic": "defense-evasion",
        "confidence": _pct(80),
    },
    "web.phpmyadmin": {
        "technique_id": "T1190",
        "technique_name": "Exploit Public-Facing Application",
        "tactic": "initial-access",
        "confidence": _pct(75),
    },
    "web.jenkins_login": {
        "technique_id": "T1078",
        "technique_name": "Valid Accounts",
        "tactic": "defense-evasion",
        "confidence": _pct(70),
    },
    "web.gitlab_login": {
        "technique_id": "T1078",
        "technique_name": "Valid Accounts",
        "tactic": "defense-evasion",
        "confidence": _pct(70),
    },
    "web.webmail_login": {
        "technique_id": "T1078",
        "technique_name": "Valid Accounts",
        "tactic": "defense-evasion",
        "confidence": _pct(75),
    },
    "web.vpn_login": {
        "technique_id": "T1133",
        "technique_name": "External Remote Services",
        "tactic": "initial-access",
        "confidence": _pct(85),
    },
    "web.api_key_harvest": {
        "technique_id": "T1528",
        "technique_name": "Steal Application Access Token",
        "tactic": "credential-access",
        "confidence": _pct(90),
    },
    "web.credential_harvest": {
        "technique_id": "T1552",
        "technique_name": "Unsecured Credentials",
        "tactic": "credential-access",
        "confidence": _pct(85),
    },
    # ── Dionaea event types ─────────────────────────────────────────────
    "dionaea.malware.download": {
        "technique_id": "T1204",
        "technique_name": "User Execution",
        "tactic": "execution",
        "confidence": _pct(90),
    },
    "dionaea.connection": {
        "technique_id": "T1046",
        "technique_name": "Network Service Discovery",
        "tactic": "discovery",
        "confidence": _pct(40),
    },
    "dionaea.smb.access": {
        "technique_id": "T1021",
        "technique_name": "Remote Services",
        "tactic": "lateral-movement",
        "confidence": _pct(65),
    },
    "dionaea.http.request": {
        "technique_id": "T1190",
        "technique_name": "Exploit Public-Facing Application",
        "tactic": "initial-access",
        "confidence": _pct(50),
    },
    "dionaea.mssql.login": {
        "technique_id": "T1110",
        "technique_name": "Brute Force",
        "tactic": "credential-access",
        "confidence": _pct(60),
    },
    "dionaea.sip.call": {
        "technique_id": "T1071.001",
        "technique_name": "Application Layer Protocol: Web Protocols",
        "tactic": "command-and-control",
        "confidence": _pct(35),
    },
    "dionaea.tftp.request": {
        "technique_id": "T1048",
        "technique_name": "Exfiltration Over Alternative Protocol",
        "tactic": "exfiltration",
        "confidence": _pct(50),
    },
    "dionaea.mssql.query": {
        "technique_id": "T1213",
        "technique_name": "Data from Information Repositories",
        "tactic": "collection",
        "confidence": _pct(55),
    },
    # ── WordPress honeypot event types ──────────────────────────────────
    "wp.login_attempt": {
        "technique_id": "T1110",
        "technique_name": "Brute Force",
        "tactic": "credential-access",
        "confidence": _pct(85),
    },
    "wp.plugin_scan": {
        "technique_id": "T1046",
        "technique_name": "Network Service Discovery",
        "tactic": "discovery",
        "confidence": _pct(55),
    },
    "wp.xmlrpc_attack": {
        "technique_id": "T1190",
        "technique_name": "Exploit Public-Facing Application",
        "tactic": "initial-access",
        "confidence": _pct(70),
    },
}


def rule_based_match(event_type: str, command: str) -> dict | None:
    command_lower = (command or "").lower()
    if "powershell" in command_lower:
        return {
            "technique_id": "T1059.001",
            "technique_name": "Command and Scripting Interpreter: PowerShell",
            "tactic": "execution",
            "confidence": _pct(90),
        }
    if any(cmd in command_lower for cmd in ["ls", "cat ", "find ", "dir "]):
        return {
            "technique_id": "T1083",
            "technique_name": "File and Directory Discovery",
            "tactic": "discovery",
            "confidence": _pct(80),
        }
    if "whoami" in command_lower or "uname" in command_lower:
        return {
            "technique_id": "T1082",
            "technique_name": "System Information Discovery",
            "tactic": "discovery",
            "confidence": _pct(85),
        }
    if "ssh " in command_lower or "scp " in command_lower:
        return {
            "technique_id": "T1021",
            "technique_name": "Remote Services",
            "tactic": "lateral-movement",
            "confidence": _pct(75),
        }
    if any(cmd in command_lower for cmd in ["nmap", "netstat", "ss -", "ip a"]):
        return {
            "technique_id": "T1046",
            "technique_name": "Network Service Discovery",
            "tactic": "discovery",
            "confidence": _pct(90),
        }
    if "chmod" in command_lower or "chown" in command_lower or "rm " in command_lower:
        return {
            "technique_id": "T1070.004",
            "technique_name": "Indicator Removal: File Deletion",
            "tactic": "defense-evasion",
            "confidence": _pct(70),
        }
    if "passwd" in command_lower or "shadow" in command_lower or "credential" in command_lower:
        return {
            "technique_id": "T1003",
            "technique_name": "OS Credential Dumping",
            "tactic": "credential-access",
            "confidence": _pct(85),
        }

    # ── Web / URL-path based rules for portal honeypot ──────────────
    if event_type in ("web", "http") or event_type.startswith("web."):
        path = (command or "").lower()
        if "wp-login" in path or "wp-login.php" in path:
            return {"technique_id": "T1078", "technique_name": "Valid Accounts", "tactic": "defense-evasion", "confidence": _pct(80)}
        if "phpmyadmin" in path or "pma" in path:
            return {"technique_id": "T1190", "technique_name": "Exploit Public-Facing Application", "tactic": "initial-access", "confidence": _pct(75)}
        if "jenkins" in path:
            return {"technique_id": "T1078", "technique_name": "Valid Accounts", "tactic": "defense-evasion", "confidence": _pct(70)}
        if "gitlab" in path or "git" in path:
            return {"technique_id": "T1078", "technique_name": "Valid Accounts", "tactic": "defense-evasion", "confidence": _pct(70)}
        if "webmail" in path or "owa" in path or "mail" in path:
            return {"technique_id": "T1078", "technique_name": "Valid Accounts", "tactic": "defense-evasion", "confidence": _pct(75)}
        if "vpn" in path:
            return {"technique_id": "T1133", "technique_name": "External Remote Services", "tactic": "initial-access", "confidence": _pct(85)}

    match = EVENT_TYPE_RULES.get(event_type)
    if match:
        return dict(match)
    return None


async def map_to_mitre(event: dict) -> dict:
    rule_match = rule_based_match(
        event_type=event.get("event_type", ""),
        command=event.get("command", ""),
    )
    if rule_match:
        return {
            "technique_id": rule_match["technique_id"],
            "technique_name": rule_match["technique_name"],
            "tactic": rule_match["tactic"],
            "confidence": rule_match["confidence"],
            "reasoning": "Rule-based mapping",
            "source": "rule",
        }

    try:
        provider = get_provider_for_module("threat_analysis", Config.all())
        prompt = MITRE_PROMPT.format(
            event_type=event.get("event_type", "unknown"),
            command=event.get("command", ""),
            raw_data=json.dumps(event.get("raw_data", {})),
        )
        response = await provider.generate(
            prompt=prompt,
            system="You map attacker commands to MITRE ATT&CK framework.",
            temperature=0.3,
        )
        data = extract_json(response.content)
        data["source"] = "ai"
        return data
    except Exception as e:
        return {
            "technique_id": None,
            "technique_name": None,
            "tactic": None,
            "confidence": 0,
            "reasoning": f"Mapping failed: {e}",
            "source": "error",
        }
