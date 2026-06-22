import logging
import random
import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.company import (
    ActiveAlert,
    AttackArtifact,
    CiCdPipeline,
    CloudInfra,
    Company,
    ContainerRegistry,
    DnsRecord,
    Document,
    Email,
    Employee,
    FirewallRule,
    LoadBalancer,
    NetworkDevice,
    PatchGap,
    Server,
    ServiceAccount,
    SourceLeak,
    SslCert,
    Subnet,
    TerraformState,
    VpnConfig,
)

logger = logging.getLogger("shadowhive")


def _naive_utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


PREFIXES = ["Dr.", "Prof.", "Mr.", "Mrs.", "Ms.", "Sir"]


def _split_name(name: str) -> tuple[str, str]:
    for p in PREFIXES:
        if name.startswith(p + " "):
            name = name[len(p) + 1 :]
            break
    parts = name.rsplit(" ", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return parts[0], ""


def _email_from_name(first: str, last: str, domain: str) -> str:
    return f"{first.lower()}.{last.lower().replace(' ', '').replace('-', '')}@{domain}"


def _domain_from_company(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower()) + ".com"


async def persist_company(db: AsyncSession, result: dict) -> dict:
    company_id = uuid.uuid4()

    domain = _domain_from_company(result.get("name", "company"))
    first_email = result.get("emails", [None])[0] if result.get("emails") else None
    if first_email and "@" in first_email.get("from", ""):
        domain = first_email["from"].split("@", 1)[1]

    company = Company(
        id=company_id,
        user_id=result.get("user_id"),
        name=result.get("name", "Unknown"),
        industry=result.get("industry", "Technology"),
        size=result.get("size", "medium"),
        description=result.get("description"),
        location_city=result.get("location"),
        location_country=None,
        founded_year=str(result.get("founded_year", "")) if result.get("founded_year") else None,
        org_chart=result.get("departments"),
        extra_data={"revenue": result.get("revenue")},
        created_at=_naive_utcnow(),
        updated_at=_naive_utcnow(),
    )
    db.add(company)

    employee_map: dict[str, uuid.UUID] = {}
    employee_rows: list[Employee] = []
    for emp in result.get("employees", []):
        name: str = emp.get("name", "Unknown")
        first, last = _split_name(name)
        email = _email_from_name(first, last, domain)
        emp_id = uuid.uuid4()
        employee_map[email] = emp_id
        employee_map[name.lower()] = emp_id
        employee_rows.append(
            Employee(
                id=emp_id,
                company_id=company_id,
                first_name=first,
                last_name=last,
                email=email,
                title=emp.get("title", ""),
                department=emp.get("department", ""),
                bio=emp.get("bio"),
                created_at=_naive_utcnow(),
                updated_at=_naive_utcnow(),
            )
        )
    for row in employee_rows:
        db.add(row)

    await db.flush()

    emails_list = result.get("emails", [])
    now = _naive_utcnow()
    for i, mail in enumerate(emails_list):
        from_addr: str = mail.get("from", "")
        to_addr: str = mail.get("to", "")

        sender_id = _lookup_employee(employee_map, from_addr)

        recipients = []
        for addr in re.split(r"[;,]\s*", to_addr):
            rid = _lookup_employee(employee_map, addr)
            if rid:
                recipients.append(str(rid))
            else:
                recipients.append(addr)

        days_ago = random.uniform(0, 30) if emails_list else 0
        hours_offset = random.uniform(0, 24)
        sent_at = now - timedelta(days=days_ago, hours=hours_offset)

        db.add(
            Email(
                id=uuid.uuid4(),
                company_id=company_id,
                sender_id=sender_id or uuid.uuid4(),
                recipient_ids=recipients,
                subject=mail.get("subject", ""),
                body=mail.get("body", ""),
                sent_at=sent_at,
                is_internal="true",
            )
        )

    for doc in result.get("documents", []):
        author_id = None
        if employee_rows:
            author_id = employee_rows[0].id
        db.add(
            Document(
                id=uuid.uuid4(),
                company_id=company_id,
                author_id=author_id,
                title=doc.get("title", ""),
                doc_type=doc.get("type", ""),
                content=doc.get("content", ""),
            )
        )

    if result.get("infrastructure"):
        await _persist_infra(db, company_id, result["infrastructure"])
    if result.get("network_depth"):
        await _persist_network_depth(db, company_id, result["network_depth"])
    if result.get("devops_pipeline"):
        await _persist_devops(db, company_id, result["devops_pipeline"])
    if result.get("security_config"):
        await _persist_security(db, company_id, result["security_config"])
    if result.get("attack_artifacts"):
        await _persist_artifacts(db, company_id, result["attack_artifacts"])

    await db.commit()

    return {
        "id": str(company_id),
        "name": company.name,
        "industry": company.industry,
        "size": company.size,
    }


def _lookup_employee(employee_map: dict[str, uuid.UUID], addr: str) -> uuid.UUID | None:
    addr_lower = addr.strip().lower()
    if addr_lower in employee_map:
        return employee_map[addr_lower]
    name_part = addr_lower.split("@")[0]
    # Try matching name_part against stored emails
    for key, val in employee_map.items():
        if "@" in key and key.startswith(name_part):
            return val
    return None


async def _persist_infra(db: AsyncSession, company_id: uuid.UUID, infra: dict):
    for s in infra.get("servers", []):
        db.add(
            Server(
                id=uuid.uuid4(),
                company_id=company_id,
                hostname=s.get("hostname", "unknown"),
                ip=s.get("ip", "0.0.0.0"),
                role=s.get("role"),
                os=s.get("os"),
                services=s.get("services"),
            )
        )
    for nd in infra.get("network_devices", []):
        db.add(
            NetworkDevice(
                id=uuid.uuid4(),
                company_id=company_id,
                hostname=nd.get("hostname", "unknown"),
                device_type=nd.get("type"),
                vendor=nd.get("vendor"),
                mgmt_ip=nd.get("mgmt_ip"),
            )
        )
    for sn in infra.get("subnets", []):
        db.add(
            Subnet(
                id=uuid.uuid4(),
                company_id=company_id,
                name=sn.get("name", "unknown"),
                cidr=sn.get("cidr", "0.0.0.0/0"),
                vlan_id=str(sn.get("vlan_id", "")) if sn.get("vlan_id") is not None else None,
            )
        )
    ci = infra.get("cloud_infra")
    if ci:
        db.add(
            CloudInfra(
                id=uuid.uuid4(),
                company_id=company_id,
                provider=ci.get("provider", "Unknown"),
                account_id=ci.get("account_id"),
                resources=ci.get("resources"),
            )
        )


async def _persist_network_depth(db: AsyncSession, company_id: uuid.UUID, nd: dict):
    for r in nd.get("dns_records", []):
        db.add(
            DnsRecord(
                id=uuid.uuid4(),
                company_id=company_id,
                name=r.get("name", ""),
                record_type=r.get("type", "A"),
                value=r.get("value", ""),
                ttl=str(r.get("ttl", "")) if r.get("ttl") is not None else None,
            )
        )
    for lb in nd.get("load_balancers", []):
        db.add(
            LoadBalancer(
                id=uuid.uuid4(),
                company_id=company_id,
                hostname=lb.get("hostname", "unknown"),
                lb_type=lb.get("type"),
                ip=lb.get("ip"),
                upstream_pool=lb.get("upstream_pool"),
                extra_data={k: v for k, v in lb.items() if k in ("listeners",) and v is not None} or None,
            )
        )
    for cert in nd.get("ssl_certs", []):
        db.add(
            SslCert(
                id=uuid.uuid4(),
                company_id=company_id,
                hostname=cert.get("hostname", "unknown"),
                issuer=cert.get("issuer"),
                subject=cert.get("subject"),
                valid_from=cert.get("valid_from"),
                valid_to=cert.get("valid_to"),
                san=cert.get("san"),
                self_signed=str(cert.get("self_signed", False)).lower(),
                weak_cipher=str(cert.get("weak_cipher", False)).lower(),
            )
        )
    for a in nd.get("active_alerts", []):
        db.add(
            ActiveAlert(
                id=uuid.uuid4(),
                company_id=company_id,
                source=a.get("source"),
                alert_type=a.get("type"),
                message=a.get("message"),
                severity=a.get("severity"),
                affected_host=a.get("affected_host"),
            )
        )


async def _persist_devops(db: AsyncSession, company_id: uuid.UUID, devops: dict):
    for p in devops.get("ci_cd_pipelines", []):
        db.add(
            CiCdPipeline(
                id=uuid.uuid4(),
                company_id=company_id,
                name=p.get("name", "unknown"),
                platform=p.get("platform"),
                url=p.get("url"),
                misconfigurations=p.get("misconfigurations"),
                extra_data={"jobs": p.get("jobs")} if p.get("jobs") else None,
            )
        )
    for leak in devops.get("source_leaks", []):
        db.add(
            SourceLeak(
                id=uuid.uuid4(),
                company_id=company_id,
                platform=leak.get("platform"),
                url=leak.get("url"),
                repo_name=leak.get("repo_name"),
                leaked_content=leak.get("leaked_content"),
                exposure_date=leak.get("exposure_date"),
                severity=leak.get("severity"),
            )
        )
    for cr in devops.get("container_registries", []):
        db.add(
            ContainerRegistry(
                id=uuid.uuid4(),
                company_id=company_id,
                registry_url=cr.get("registry_url"),
                provider=cr.get("provider"),
                extra_data={"repositories": cr.get("repositories")} if cr.get("repositories") else None,
            )
        )
    ts = devops.get("terraform_state")
    if ts and isinstance(ts, dict):
        db.add(
            TerraformState(
                id=uuid.uuid4(),
                company_id=company_id,
                backend_type=ts.get("backend_type"),
                state_file_url=ts.get("state_file_url"),
                resources=ts.get("resources"),
                exposed_secrets=ts.get("exposed_secrets"),
            )
        )


async def _persist_security(db: AsyncSession, company_id: uuid.UUID, sec: dict):
    for fr in sec.get("firewall_rules", []):
        db.add(
            FirewallRule(
                id=uuid.uuid4(),
                company_id=company_id,
                source=fr.get("source"),
                destination=fr.get("destination"),
                port=fr.get("port"),
                protocol=fr.get("protocol"),
                action=fr.get("action"),
                purpose=fr.get("purpose"),
            )
        )
    for pg in sec.get("patch_gaps", []):
        db.add(
            PatchGap(
                id=uuid.uuid4(),
                company_id=company_id,
                hostname=pg.get("hostname"),
                missing_patch=pg.get("missing_patch"),
                severity=pg.get("severity"),
            )
        )
    for sa in sec.get("service_accounts", []):
        db.add(
            ServiceAccount(
                id=uuid.uuid4(),
                company_id=company_id,
                username=sa.get("username", "unknown"),
                privilege_level=sa.get("privilege_level"),
                used_by=sa.get("used_by"),
            )
        )
    vpn = sec.get("vpn_config")
    if vpn and isinstance(vpn, dict):
        db.add(
            VpnConfig(
                id=uuid.uuid4(),
                company_id=company_id,
                provider=vpn.get("provider"),
                endpoint=vpn.get("endpoint"),
                auth_method=vpn.get("auth_method"),
            )
        )
    extra = {}
    for k in ("edr_status", "edr_coverage"):
        if sec.get(k):
            extra[k] = sec[k]
    if extra:
        await db.execute(
            __import__("sqlalchemy").update(Server).where(Server.company_id == company_id).values(extra_data=extra)
        )


async def _persist_artifacts(db: AsyncSession, company_id: uuid.UUID, artifacts: list):
    for art in artifacts:
        db.add(
            AttackArtifact(
                id=uuid.uuid4(),
                company_id=company_id,
                artifact_type=art.get("type", "unknown"),
                name=art.get("name", ""),
                location=art.get("location"),
                content_excerpt=art.get("content_excerpt"),
                severity=art.get("severity"),
                description=art.get("description"),
            )
        )
