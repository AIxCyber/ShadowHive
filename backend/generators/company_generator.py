import asyncio
import json as json_mod
import time
from collections.abc import Callable, Coroutine

from backend.ai import get_provider_for_module
from backend.utils.config import Config
from backend.utils.json_parser import extract_json

ProgressCb = Callable[[int, str], Coroutine]
HeartbeatCb = Callable[[int], Coroutine]

# Phase timeouts (seconds) — generous for CPU inference (~1-2 tok/s on 8B model)
PHASE_TIMEOUTS = {
    2048: 1800,  # 30 min
    3072: 3600,  # 60 min
    4096: 5400,  # 90 min
    8192: 9000,  # 150 min
}


def _build_profile_prompt(industry: str, size: str, seed: str, overrides: dict | None) -> str:
    name_hint = ""
    desc_hint = ""
    location_hint = ""
    if overrides:
        if overrides.get("company_name"):
            name_hint = f'\nUse the EXACT company name: "{overrides["company_name"]}"'
        if overrides.get("description"):
            desc_hint = f"\nBackground context to incorporate into the description: {overrides['description']}"
        if overrides.get("location"):
            location_hint = f"\nSet the location to: {overrides['location']}"

    dept_range = {"small": "3-5", "medium": "5-8", "large": "8-12"}.get(size, "5-8")

    return f"""Generate a fictional company profile for cybersecurity tabletop exercises and training simulations.

Industry: {industry}
Size: {size}
Seed: {seed}
{name_hint}{desc_hint}{location_hint}

Return JSON:
{{
  "name": "Company name",
  "description": "2-3 sentence description",
  "location": "City, State/Country",
  "founded_year": 2010,
  "revenue": "$X",
  "industry": "{industry}",
  "size": "{size}",
  "departments": [
    {{"name": "Dept Name", "head_count": 5}}
  ]
}}

For {size} size, generate {dept_range} departments.
ONLY return valid JSON."""


def _build_employee_prompt(profile: dict, industry: str, size: str = "medium") -> str:
    dept_names = ", ".join(d["name"] for d in profile.get("departments", []))
    emp_range = {"small": "3-6", "medium": "5-10", "large": "8-20"}.get(size, "5-10")
    return f"""Generate employees for a fictional company used in cybersecurity training simulations.

Company: {profile["name"]}
Industry: {industry}
Location: {profile.get("location", "")}
Departments: {dept_names}
Company size: {size}

Return a JSON array of employees:
[
  {{
    "name": "Full Name",
    "title": "Job Title",
    "department": "Department",
    "bio": "2-3 sentence professional bio"
  }}
]

Rules:
- Generate {emp_range} employees per department
- Names must match the location's cultural background
- Titles must be realistic for the industry
- Bios should be realistic professional summaries
- ONLY return valid JSON array"""


def _build_email_prompt(
    profile: dict, industry: str, employees: list, overrides: dict | None, size: str = "medium"
) -> str:
    emp_summary = "\n".join(f"- {e['name']}, {e.get('title', '')} ({e.get('department', '')})" for e in employees)
    tech_hint = ""
    if overrides and overrides.get("technologies"):
        tech_list = ", ".join(overrides["technologies"])
        tech_hint = f"\nThe company uses these technologies: {tech_list}. Reference them in email discussions."

    weakness_rule = _weakness_rule(overrides, "email")

    email_range = {"small": "3-5", "medium": "5-10", "large": "10-20"}.get(size, "5-10")
    return f"""Generate realistic internal email threads for a fictional company used in cybersecurity training simulations.

Company: {profile["name"]}
Industry: {industry}
Company size: {size}
Employees:
{emp_summary}{tech_hint}

Return a JSON array of emails:
[
  {{
    "from": "name@company.com",
    "to": "name@company.com",
    "subject": "email subject",
    "body": "email body text"
  }}
]

Rules:
- Generate {email_range} realistic email threads
- Emails should discuss business operations and projects relevant to the {industry} industry
- Use realistic corporate communication styles
- From/to must use actual employee names from the provided list with a plausible domain
{weakness_rule}
- ONLY return valid JSON array"""


def _build_doc_prompt(profile: dict, industry: str, overrides: dict | None, size: str = "medium") -> str:
    tech_hint = ""
    if overrides and overrides.get("technologies"):
        tech_list = ", ".join(overrides["technologies"])
        tech_hint = f"\nThe company uses these technologies: {tech_list}. Reference them in document content."

    weakness_rule = _weakness_rule(overrides, "document")
    doc_range = {"small": "3-4", "medium": "5-8", "large": "8-15"}.get(size, "5-8")
    para_range = {"small": "3-5", "medium": "3-5", "large": "2-4"}.get(size, "3-5")

    return f"""Generate realistic business documents for a fictional company used in cybersecurity training simulations.

Company: {profile["name"]}
Industry: {industry}
Company size: {size}
Description: {profile.get("description", "")}{tech_hint}

Return a JSON array of documents:
[
  {{
    "title": "Document Title",
    "type": "Security Report | Financial Report | Internal Memo | Meeting Notes | Technical Spec",
    "risk_level": "confidential | internal | public",
    "content": "{para_range} paragraphs of realistic business content"
  }}
]

Rules:
- Generate {doc_range} documents with different types
- Content must be realistic and relevant to the {industry} industry
- Include specific details, dates, metrics where appropriate
{weakness_rule}
- ONLY return valid JSON array"""


def _build_infra_prompt(profile: dict, industry: str, overrides: dict | None, size: str = "medium") -> str:
    tech_hint = ""
    if overrides and overrides.get("technologies"):
        tech_list = ", ".join(overrides["technologies"])
        tech_hint = f"\nThe company uses these technologies: {tech_list}. Include relevant infrastructure for them."

    posture = _posture_label(overrides)

    server_range = {"small": "5-8", "medium": "10-20", "large": "20-40"}.get(size, "10-20")
    netdev_range = {"small": "3-5", "medium": "5-10", "large": "8-15"}.get(size, "5-10")

    return f"""Generate a realistic network infrastructure for a fictional company used in cybersecurity training simulations.

Company: {profile["name"]}
Industry: {industry}
Company size: {size}
Location: {profile.get("location", "")}
Departments: {", ".join(d["name"] for d in profile.get("departments", []))}
Security posture: {posture}{tech_hint}

Return JSON:
{{
  "domain": "company.internal",
  "servers": [
    {{
      "hostname": "HOSTNAME-01",
      "ip": "10.10.x.x",
      "role": "DC | Web | DB | File | Mail | App",
      "os": "Windows Server 2022 | Ubuntu 22.04",
      "services": ["port/service list"]
    }}
  ],
  "network_devices": [
    {{
      "hostname": "sw-01",
      "type": "switch | router | firewall | AP",
      "vendor": "Cisco | Ubiquiti | pfSense",
      "mgmt_ip": "10.10.255.x"
    }}
  ],
  "subnets": [
    {{
      "name": "DMZ | Internal | DB | Management",
      "cidr": "10.10.x.0/24",
      "vlan_id": 100
    }}
  ],
  "cloud_infra": {{
    "provider": "AWS | Azure",
    "account_id": "12-digit account",
    "resources": ["S3 bucket", "RDS instance", "EKS cluster"]
  }}
}}

Rules:
- Generate {server_range} servers covering different roles appropriate for {industry}
- All IPs must be in RFC1918 private ranges
- Hostnames follow a realistic naming convention
- Network devices match the company size ({netdev_range} devices)
- Cloud section can be null if industry doesn't suggest cloud use
- ONLY return valid JSON"""


def _build_security_prompt(
    profile: dict, industry: str, infra: dict, overrides: dict | None, size: str = "medium"
) -> str:
    posture_label = _posture_label(overrides)
    posture_guide = _security_posture_rules(overrides)

    server_summary = (
        "\n".join(
            f"- {s['hostname']} ({s.get('ip', '')}) role={s.get('role', '')} os={s.get('os', '')}"
            for s in infra.get("servers", [])
        )
        if infra.get("servers")
        else "None listed"
    )

    fw_range = {"small": "5-8", "medium": "8-15", "large": "15-30"}.get(size, "8-15")

    return f"""Generate security configuration details for a fictional company used in cybersecurity training simulations.

Company: {profile["name"]}
Industry: {industry}
Company size: {size}
Security posture: {posture_label}
{posture_guide}

Servers in the environment:
{server_summary}

Return JSON:
{{
  "firewall_rules": [
    {{
      "source": "0.0.0.0/0 | subnet | specific IP",
      "destination": "server or subnet",
      "port": "443",
      "protocol": "TCP",
      "action": "ALLOW | DENY",
      "purpose": "description"
    }}
  ],
  "edr_status": "CrowdStrike Falcon | SentinelOne | Defender | None",
  "edr_coverage": "All servers | Only critical | None",
  "patch_gaps": [
    {{
      "hostname": "affected server",
      "missing_patch": "KB number or CVE",
      "severity": "Critical | High | Medium"
    }}
  ],
  "service_accounts": [
    {{
      "username": "svc_account_name",
      "privilege_level": "Domain Admin | Local Admin | Standard",
      "used_by": "application or service"
    }}
  ],
  "vpn_config": {{
    "provider": "OpenVPN | WireGuard | Cisco AnyConnect",
    "endpoint": "vpn.company.com",
    "auth_method": "MFA | Certificate | Password only"
  }}
}}

Rules:
- Generate {fw_range} firewall rules that form a coherent policy
- EDR status must match the security posture
- Patch gaps: 0-1 for mature, 1-2 for startup, 2-3 for neglected
- Include 1-2 service accounts, one of which may be over-privileged for neglected posture
- ONLY return valid JSON"""


def _build_artifacts_prompt(
    profile: dict, employees: list, infra: dict, overrides: dict | None, size: str = "medium"
) -> str:
    posture_label = _posture_label(overrides)
    emp_count = {"small": 8, "medium": 15, "large": 25}.get(size, 15)
    emp_names = "\n".join(
        f"- {e['name']} ({e.get('title', '')}, {e.get('department', '')})" for e in employees[:emp_count]
    )
    server_ips = [s.get("ip", "x.x.x.x") for s in (infra.get("servers") or [])[:5]]

    closeness = "aggressive" if (overrides or {}).get("security_posture") == "neglected" else "moderate"
    base_count = {"neglected": "3-5", "startup": "2-4", "mature": "1-2", "default": "2-4"}
    count = base_count.get((overrides or {}).get("security_posture", "default"), "2-4")
    size_mult = {"small": "", "medium": "", "large": " (increase by 1-2 since this is a large company)"}.get(size, "")

    return f"""Generate attack artifacts and honeytokens for a fictional company used in cybersecurity training simulations.
These are deliberately placed findings that an attacker would discover during post-exploitation.

Company: {profile["name"]}
Industry: {profile.get("industry", "")}
Company size: {size}
Security posture: {posture_label}
Leak closeness: {closeness}
Artifact count: {count}{size_mult}

Key employees:
{emp_names}

Server IPs in environment: {", ".join(server_ips)}

Return a JSON array of artifacts:
[
  {{
    "type": "config_file | ssh_key | sql_dump | chat_log | ci_cd_token | browser_export | password_manager | backup_file",
    "name": "filename or artifact name",
    "location": "file path or description of where it was found",
    "content_excerpt": "short excerpt showing the sensitive data",
    "severity": "critical | high | medium",
    "description": "what an attacker could do with this"
  }}
]

Rules:
- Generate {count} artifacts appropriate for a {posture_label} company{size_mult}
- For neglected posture: include something tempting like a domain admin password or AWS keys
- For startup posture: include dev credentials or a staging DB password
- For mature posture: include only low-severity items like a stale API token
- Filenames and paths must be realistic
- Content excerpts should look authentic but clearly indicate they are training simulations
- Reference real employee names and server IPs where appropriate
- ONLY return valid JSON array"""


def _build_network_depth_prompt(
    profile: dict, industry: str, infra: dict, overrides: dict | None, size: str = "medium"
) -> str:
    posture_label = _posture_label(overrides)
    server_summary = (
        "\n".join(f"- {s['hostname']} ({s.get('ip', '')}) role={s.get('role', '')}" for s in infra.get("servers", []))
        if infra.get("servers")
        else "None listed"
    )
    domain = infra.get("domain", "company.internal")

    dns_range = {"small": "5-8", "medium": "10-20", "large": "20-40"}.get(size, "10-20")
    lb_range = {"small": "1", "medium": "1-2", "large": "2-4"}.get(size, "1-2")
    cert_range = {"small": "2-3", "medium": "3-5", "large": "5-10"}.get(size, "3-5")
    alert_range = {"small": "2-4", "medium": "4-8", "large": "8-15"}.get(size, "4-8")

    return f"""Generate internal network services for a fictional company used in cybersecurity training simulations.

Company: {profile["name"]}
Industry: {industry}
Company size: {size}
Domain: {domain}
Security posture: {posture_label}

Servers:
{server_summary}

Return JSON:
{{
  "dns_records": [
    {{
      "name": "hostname.company.internal",
      "type": "A | AAAA | CNAME | MX | SRV",
      "value": "10.10.x.x | alias.company.internal",
      "ttl": 3600
    }}
  ],
  "load_balancers": [
    {{
      "hostname": "lb-01.company.internal",
      "type": "nginx | haproxy | aws_alb",
      "ip": "10.10.x.x",
      "upstream_pool": ["web-01:80", "web-02:80"],
      "listeners": [{{"port": 443, "protocol": "HTTPS", "backend": "web-pool"}}]
    }}
  ],
  "ssl_certs": [
    {{
      "hostname": "www.company.internal",
      "issuer": "Let's Encrypt | Internal CA | Self-Signed",
      "subject": "CN=www.company.internal",
      "valid_from": "2024-01-01",
      "valid_to": "2025-01-01",
      "san": ["www.company.internal", "company.internal"],
      "self_signed": false,
      "weak_cipher": false
    }}
  ],
  "active_alerts": [
    {{
      "source": "Snort | Windows Event ID | pfSense | CrowdStrike",
      "type": "IDS Alert | Firewall Block | Event Log | EDR Detection",
      "message": "description of the alert",
      "severity": "critical | high | medium | low",
      "affected_host": "server hostname or IP",
      "timestamp": "relative timestamp"
    }}
  ]
}}

Rules:
- Generate {dns_range} DNS records covering A, CNAME, and MX types mapping the server hostnames to their IPs
- Generate {lb_range} load balancers or reverse proxies appropriate for the company size
- Generate {cert_range} SSL certificates — for neglected posture include at least 1 self-signed or expired cert
- Generate {alert_range} active alerts consistent with the security posture:
  - Neglected: critical alerts about malware, multiple failed logins, CVE exploitation attempts
  - Mature: low-severity informational alerts only
  - Startup: medium-severity alerts about misconfigurations, unusual outbound traffic
- Only use IPs and hostnames from the provided server list
- ONLY return valid JSON"""


def _build_devops_prompt(
    profile: dict, industry: str, infra: dict, overrides: dict | None, size: str = "medium"
) -> str:
    posture_label = _posture_label(overrides)
    domain = infra.get("domain", "company.internal")
    server_roles = [s.get("role", "") for s in (infra.get("servers") or [])[:6]]
    tech_hint = ""
    if overrides and overrides.get("technologies"):
        tech_hint = f"\nThe company uses: {', '.join(overrides['technologies'])}."

    pipeline_range = {"small": "1-2", "medium": "2-3", "large": "3-5"}.get(size, "2-3")
    leak_range = {"small": "1", "medium": "1-3", "large": "2-5"}.get(size, "1-3")
    registry_range = {"small": "1-2", "medium": "2-3", "large": "3-5"}.get(size, "2-3")

    return f"""Generate CI/CD pipeline, source leak, container registry, and Terraform state data for a fictional company used in cybersecurity training simulations.

Company: {profile["name"]}
Industry: {industry}
Company size: {size}
Domain: {domain}
Security posture: {posture_label}{tech_hint}
Server roles present: {", ".join(server_roles)}

Return JSON:
{{
  "ci_cd_pipelines": [
    {{
      "name": "pipeline-name",
      "platform": "Jenkins | GitHub Actions | GitLab CI",
      "url": "https://jenkins.company.internal/job/pipeline",
      "misconfigurations": ["description of security issue"],
      "jobs": [
        {{"name": "build", "stage": "Build", "script_summary": "key commands run"}},
        {{"name": "deploy", "stage": "Deploy", "script_summary": "deployment commands"}}
      ]
    }}
  ],
  "source_leaks": [
    {{
      "platform": "GitHub | Pastebin | GitLab Gist",
      "url": "https://github.com/user/repo",
      "repo_name": "leaked-repo-name",
      "leaked_content": "brief excerpt of what was leaked",
      "exposure_date": "2024-01-15",
      "severity": "critical | high | medium | low"
    }}
  ],
  "container_registries": [
    {{
      "registry_url": "registry.company.internal:5000",
      "provider": "Docker Hub | ECR | GCR | Harbor",
      "repositories": [
        {{
          "name": "service-name",
          "tags": ["latest", "v1.0.0"],
          "vulnerability_count": 5,
          "critical_vulns": 1
        }}
      ]
    }}
  ],
  "terraform_state": {{
    "backend_type": "S3 | GCS | Azurerm",
    "state_file_url": "s3://tf-state-bucket/terraform.tfstate",
    "resources": ["resource.type.name"],
    "exposed_secrets": ["secret_name"]
  }}
}}

Rules:
- Generate {pipeline_range} CI/CD pipelines appropriate for the company's industry and technology stack
- Generate {leak_range} source leaks consistent with the security posture
- Generate {registry_range} container registries with 1-3 repositories each
- Include terraform_state (can be null if no cloud infra)
- For {posture_label} posture:
  - Neglected: exposed secrets in pipeline configs, critical source leaks with credentials, vulnerable images with critical CVEs, Terraform state with plaintext secrets
  - Startup: minor misconfigurations like missing approval gates, one medium-severity source leak, some high-severity vulnerabilities
  - Mature: no misconfigurations (or trivial), no significant leaks, few low-severity vulns, locked Terraform state
  - Default: moderate posture with 1-2 minor issues
- Reference the company domain {domain} and server roles where appropriate
- ONLY return valid JSON"""


def _weakness_rule(overrides: dict | None, kind: str) -> str:
    posture = "default"
    if overrides:
        posture = overrides.get("security_posture", "default")

    rules = {
        "mature": (
            "The company has a mature security team and strong security culture.\n"
            "Include at most 1 very minor weakness (e.g. a routine security notice, "
            "a phishing test announcement, or a soon-to-expire certificate reminder)."
        ),
        "startup": (
            "The company is a fast-growing startup with a lean security posture.\n"
            f"Deliberately include 1-2 plausible security weaknesses in this {kind}. "
            "Examples: hardcoded API keys in internal notes, a developer mentioning "
            "they pushed credentials to a private repo, default cloud bucket permissions, "
            "or a staging server with no auth."
        ),
        "neglected": (
            "The company has severely neglected security practices — outdated systems, "
            "weak passwords, and poor operational security.\n"
            f"Deliberately include 2-3 realistic security weaknesses in this {kind}. "
            "Examples: an IT admin emailing plaintext passwords, a config file with "
            "default credentials, deprecated SSL/TLS configs, exposed S3 bucket URLs, "
            "root credentials in a Confluence page, or mentions of unpatched CVEs."
        ),
        "default": "Include 1 plausible security weakness appropriate for a typical mid-market company.",
    }
    return rules.get(posture, rules["default"])


def _posture_label(overrides: dict | None) -> str:
    if overrides:
        return overrides.get("security_posture", "default")
    return "default"


def _security_posture_rules(overrides: dict | None) -> str:
    if overrides:
        posture = overrides.get("security_posture", "default")
    else:
        posture = "default"
    rules = {
        "mature": "The company prioritizes security: MFA is enforced, all servers have EDR, patching is regular.",
        "startup": "The company is growing fast: basic EDR exists, some servers may not be covered, dev teams have elevated access.",
        "neglected": "Security is severely neglected: no EDR on most servers, default passwords in use, patches are months behind, domain admin creds are widely shared.",
        "default": "Standard mid-market company with typical security practices.",
    }
    return rules.get(posture, rules["default"])


async def _safe_generate(
    provider,
    prompt: str,
    system: str,
    max_tokens: int,
    retries: int = 1,
    on_heartbeat: HeartbeatCb | None = None,
) -> dict | list:
    logger = __import__("logging").getLogger("shadowhive")
    timeout = PHASE_TIMEOUTS.get(max_tokens, 3600)

    async def _heartbeat() -> None:
        """Update task message every 15s during generation so the user sees the task is alive."""
        start = time.time()
        try:
            while True:
                await asyncio.sleep(15)
                if on_heartbeat:
                    await on_heartbeat(int(time.time() - start))
        except asyncio.CancelledError:
            pass

    for attempt in range(retries + 1):
        try:
            hb_task = asyncio.create_task(_heartbeat())
            try:
                response = await asyncio.wait_for(
                    provider.generate(
                        prompt=prompt,
                        system=system,
                        max_tokens=max_tokens,
                        on_token=None,
                    ),
                    timeout=timeout,
                )
            finally:
                hb_task.cancel()
                try:
                    await hb_task
                except (asyncio.CancelledError, Exception):
                    pass

            return extract_json(response.content)

        except json_mod.JSONDecodeError as e:
            if attempt < retries:
                logger.warning(
                    f"JSON parse failed (attempt {attempt + 1}/{retries + 1}), retrying with stricter prompt"
                )
                prompt = (
                    prompt.rstrip()
                    + "\n\nCRITICAL: Your previous response contained invalid JSON. Return ONLY valid JSON this time. No markdown formatting. No backticks. Only raw JSON."
                )
            else:
                logger.warning(f"JSON parse failed after {retries + 1} attempts: {e}")
                logger.warning(f"Raw response ({len(response.content)} chars): {response.content[:500]!r}")
        except TimeoutError:
            logger.warning(f"Generation timed out after {timeout}s (attempt {attempt + 1}/{retries + 1})")
            if attempt < retries:
                prompt = (
                    prompt.rstrip()
                    + "\n\nCRITICAL: Your previous response took too long. Return a COMPLETE valid JSON response quickly this time. No markdown. No backticks. Only raw JSON."
                )
        except Exception as e:
            logger.warning(f"Generation failed (attempt {attempt + 1}/{retries + 1}): {e}")
            if attempt < retries:
                await asyncio.sleep(2)
    return None


async def generate_company(
    industry: str = "Technology",
    size: str = "medium",
    seed: str | None = None,
    on_progress: ProgressCb | None = None,
    overrides: dict | None = None,
) -> dict:
    provider = get_provider_for_module("company_generation", Config.all())
    seed_val = seed or "default"
    system = "You are a corporate identity generator for security training simulations."
    enrich = (overrides or {}).get("enrich", False)

    # Phase 1: Company profile (10%)
    if on_progress:
        await on_progress(10, "Generating company profile...")
    profile_prompt = _build_profile_prompt(industry, size, seed_val, overrides)
    profile = await _safe_generate(
        provider,
        profile_prompt,
        system,
        2048,
        on_heartbeat=(lambda s: on_progress(10, f"Generating company profile... ({s}s)")) if on_progress else None,
    )
    if not profile or not isinstance(profile, dict):
        logger = __import__("logging").getLogger("shadowhive")
        logger.warning("Profile generation failed, using fallback")
        profile = {
            "name": f"{industry}-{size}-{seed_val}",
            "description": f"A {size} {industry} company.",
            "location": "Unknown",
            "founded_year": 2020,
            "revenue": "$0",
            "industry": industry,
            "size": size,
            "departments": [{"name": "General", "head_count": 5}],
        }

    # Phase 2: Employees (35%)
    if on_progress:
        await on_progress(35, "Generating employees...")
    emp_prompt = _build_employee_prompt(
        profile,
        profile.get("industry", industry),
        size=size,
    )
    employees = await _safe_generate(
        provider,
        emp_prompt,
        system,
        3072,
        on_heartbeat=(lambda s: on_progress(35, f"Generating employees... ({s}s)")) if on_progress else None,
    )
    if not isinstance(employees, list):
        employees = []

    # Phase 3: Emails (60%)
    if on_progress:
        await on_progress(60, "Generating email threads...")
    email_prompt = _build_email_prompt(profile, profile.get("industry", industry), employees, overrides, size=size)
    emails = await _safe_generate(
        provider,
        email_prompt,
        system,
        3072,
        on_heartbeat=(lambda s: on_progress(60, f"Generating email threads... ({s}s)")) if on_progress else None,
    )
    if not isinstance(emails, list):
        emails = []

    # Phase 4: Documents (85%)
    if on_progress:
        await on_progress(85, "Generating documents...")
    doc_prompt = _build_doc_prompt(profile, profile.get("industry", industry), overrides, size=size)
    doc_max_tokens = 8192 if size == "large" else 4096
    documents = await _safe_generate(
        provider,
        doc_prompt,
        system,
        doc_max_tokens,
        on_heartbeat=(lambda s: on_progress(85, f"Generating documents... ({s}s)")) if on_progress else None,
    )
    if not isinstance(documents, list):
        documents = []

    result = {
        **profile,
        "employees": employees,
        "emails": emails,
        "documents": documents,
    }

    # ── Enrichment phases (opt-in) ──────────────────────────────────────

    if enrich:
        # Phase 5: Network Infrastructure (90%)
        if on_progress:
            await on_progress(90, "Generating network infrastructure...")
        infra_prompt = _build_infra_prompt(profile, profile.get("industry", industry), overrides, size=size)
        infra = await _safe_generate(
            provider,
            infra_prompt,
            system,
            3072,
            on_heartbeat=(lambda s: on_progress(90, f"Generating network infrastructure... ({s}s)"))
            if on_progress
            else None,
        )
        if not isinstance(infra, dict):
            infra = {}
        result["infrastructure"] = infra

        # Phase 5b: Network Depth — DNS, load balancers, SSL certs, active alerts (92%)
        if on_progress:
            await on_progress(92, "Generating network services (DNS, LB, certs, alerts)...")
        nd_prompt = _build_network_depth_prompt(profile, profile.get("industry", industry), infra, overrides, size=size)
        nd = await _safe_generate(
            provider,
            nd_prompt,
            system,
            3072,
            on_heartbeat=(lambda s: on_progress(92, f"Generating network services... ({s}s)")) if on_progress else None,
        )
        if isinstance(nd, dict):
            for key in ("dns_records", "load_balancers", "ssl_certs", "active_alerts"):
                if key not in nd or not isinstance(nd[key], list):
                    nd[key] = []
            result["network_depth"] = nd
        else:
            result["network_depth"] = {"dns_records": [], "load_balancers": [], "ssl_certs": [], "active_alerts": []}

        # Phase 5c: CI/CD Pipelines, Source Leaks, Container Registries, Terraform State (93%)
        if on_progress:
            await on_progress(93, "Generating CI/CD pipelines and DevOps data...")
        devops_prompt = _build_devops_prompt(profile, profile.get("industry", industry), infra, overrides, size=size)
        devops = await _safe_generate(
            provider,
            devops_prompt,
            system,
            3072,
            on_heartbeat=(lambda s: on_progress(93, f"Generating CI/CD... ({s}s)")) if on_progress else None,
        )
        if isinstance(devops, dict):
            for key in ("ci_cd_pipelines", "source_leaks", "container_registries"):
                if key not in devops or not isinstance(devops[key], list):
                    devops[key] = []
            if "terraform_state" not in devops or not isinstance(devops.get("terraform_state"), dict):
                devops["terraform_state"] = None
            result["devops_pipeline"] = devops
        else:
            result["devops_pipeline"] = {
                "ci_cd_pipelines": [],
                "source_leaks": [],
                "container_registries": [],
                "terraform_state": None,
            }

        # Phase 6: Security Configuration (95%)
        if on_progress:
            await on_progress(95, "Generating security configuration...")
        sec_prompt = _build_security_prompt(profile, profile.get("industry", industry), infra, overrides, size=size)
        security = await _safe_generate(
            provider,
            sec_prompt,
            system,
            3072,
            on_heartbeat=(lambda s: on_progress(95, f"Generating security configuration... ({s}s)"))
            if on_progress
            else None,
        )
        if not isinstance(security, dict):
            security = {}
        result["security_config"] = security

        # Phase 7: Attack Artifacts (99%)
        if on_progress:
            await on_progress(99, "Generating attack artifacts...")
        art_prompt = _build_artifacts_prompt(profile, employees, infra, overrides, size=size)
        artifacts = await _safe_generate(
            provider,
            art_prompt,
            system,
            4096,
            on_heartbeat=(lambda s: on_progress(99, f"Generating attack artifacts... ({s}s)")) if on_progress else None,
        )
        if not isinstance(artifacts, list):
            artifacts = []
        result["attack_artifacts"] = artifacts

    return result
