import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from backend.auth import get_optional_user, is_auth_enabled
from backend.database import get_session
from backend.generators.company_generator import generate_company
from backend.models.company import (
    ActiveAlert,
    AttackArtifact,
    CiCdPipeline,
    CloudInfra,
    Company,
    CompanyProfile,
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
from backend.models.user import User
from backend.services.company_persister import persist_company
from backend.services.task_manager import TaskStatus, task_manager
from backend.utils.timezone import format_dt, get_user_tz

router = APIRouter(prefix="/api/companies", tags=["companies"])
logger = logging.getLogger("shadowhive")


def _naive_utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class GenerateRequest(BaseModel):
    industry: str = "Technology"
    size: str = "medium"
    seed: str | None = None
    overrides: dict[str, Any] | None = None
    enrich: bool = False


class ProfileCreate(BaseModel):
    name: str
    industry: str | None = None
    size: str | None = None
    company_name: str | None = None
    description: str | None = None
    location: str | None = None
    technologies: list[str] | None = None
    security_posture: str | None = "default"


# ── Generate ──────────────────────────────────────────────────────────────


@router.post("/generate")
async def generate_company_route(
    body: GenerateRequest,
    user: User | None = Depends(get_optional_user),
):
    overrides = body.overrides or {}
    if body.enrich:
        overrides["enrich"] = True
    user_id = str(user.id) if user and is_auth_enabled() else None
    params = {
        "industry": body.industry,
        "size": body.size,
        "seed": body.seed or "default",
        "overrides": overrides,
    }
    task = await task_manager.create("company_generation", params, user_id=user_id)
    await task_manager.update(
        task.id, status="running", progress=0.0, message="Starting generation...", started_at=_naive_utcnow()
    )

    async def run():
        try:

            async def on_progress(pct: int, msg: str):
                t = await task_manager.get(task.id)
                if t:
                    await t._paused.wait()
                await task_manager.update(task.id, progress=float(pct), message=msg)

            result = await generate_company(
                industry=body.industry,
                size=body.size,
                seed=body.seed,
                on_progress=on_progress,
                overrides=overrides,
            )

            result["user_id"] = user_id

            try:
                async for db in get_session():
                    persisted = await persist_company(db, result)
                    result["persisted_id"] = persisted["id"]
                    logger.info(f"Persisted company {persisted['id']} — {persisted['name']}")
            except Exception as e:
                logger.error(f"Failed to persist company: {type(e).__name__}: {e}", exc_info=True)
                result["persist_error"] = f"{type(e).__name__}: {e}"

            await task_manager.update(
                task.id,
                status="completed",
                progress=100.0,
                message="Generation complete",
                result=result,
                completed_at=_naive_utcnow(),
            )
        except asyncio.CancelledError:
            await task_manager.update(
                task.id, status="cancelled", message="Cancelled by user", completed_at=_naive_utcnow()
            )
        except Exception as e:
            logger.error(f"Generation failed for task {task.id}: {type(e).__name__}: {e}", exc_info=True)
            await task_manager.update(
                task.id, status="failed", error=f"{type(e).__name__}: {e}", completed_at=_naive_utcnow()
            )

    task_manager.register(task.id, run())
    return {"task_id": task.id}


# ── Task lifecycle ────────────────────────────────────────────────────────


@router.post("/tasks/{task_id}/pause")
async def pause_task(task_id: str):
    await task_manager.pause(task_id)
    task = await task_manager.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.to_dict()


@router.post("/tasks/{task_id}/resume")
async def resume_task(task_id: str):
    await task_manager.resume(task_id)
    task = await task_manager.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.to_dict()


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    await task_manager.cancel(task_id)
    task = await task_manager.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.to_dict()


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    await task_manager.delete(task_id)
    return {"deleted": True}


@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    task = await task_manager.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    resp = task.to_dict()
    status_val = task.status.value if isinstance(task.status, TaskStatus) else task.status
    if status_val == "completed" and task.result:
        resp["result"] = task.result
    return resp


@router.get("/tasks")
async def list_tasks():
    tasks = await task_manager.list_tasks()
    return [t.to_dict() for t in tasks]


# ── Saved Profiles (templates) ────────────────────────────────────────────


@router.post("/profiles")
async def create_profile(
    body: ProfileCreate,
    request: Request,
    user: User | None = Depends(get_optional_user),
):
    async for db in get_session():
        profile = CompanyProfile(
            id=uuid.uuid4(),
            user_id=str(user.id) if user and is_auth_enabled() else None,
            name=body.name,
            industry=body.industry,
            size=body.size,
            company_name=body.company_name,
            description=body.description,
            location=body.location,
            technologies=body.technologies,
            security_posture=body.security_posture or "default",
        )
        db.add(profile)
        await db.commit()
        return _profile_dict(profile, request)


@router.get("/profiles")
async def list_profiles(request: Request):
    async for db in get_session():
        rows = (await db.execute(select(CompanyProfile).order_by(CompanyProfile.updated_at.desc()))).scalars().all()
        return [_profile_dict(r, request) for r in rows]


@router.get("/profiles/{profile_id}")
async def get_profile(profile_id: str, request: Request):
    async for db in get_session():
        profile = await db.get(CompanyProfile, uuid.UUID(profile_id))
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        return _profile_dict(profile, request)


@router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: str):
    async for db in get_session():
        profile = await db.get(CompanyProfile, uuid.UUID(profile_id))
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        await db.delete(profile)
        await db.commit()
        return {"deleted": True}


# ── Persisted companies ──────────────────────────────────────────────────


@router.get("/health")
async def health():
    return {"status": "ok", "service": "ShadowHive API"}


@router.get("")
async def list_companies(
    request: Request,
    user: User | None = Depends(get_optional_user),
):
    async for db in get_session():
        query = select(Company).order_by(Company.created_at.desc())
        if user and is_auth_enabled() and not user.is_admin:
            query = query.where(Company.user_id == str(user.id))
        rows = (await db.execute(query)).scalars().all()
        return [_company_summary(r, request) for r in rows]


@router.get("/{company_id}")
async def get_company(company_id: str, request: Request, user: User | None = Depends(get_optional_user)):
    async for db in get_session():
        cid = uuid.UUID(company_id)
        company = await db.get(Company, cid)
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
        if user and is_auth_enabled() and not user.is_admin and company.user_id != str(user.id):
            raise HTTPException(status_code=403, detail="Access denied")

        employees = (await db.execute(select(Employee).where(Employee.company_id == cid))).scalars().all()

        emails = (
            (await db.execute(select(Email).where(Email.company_id == cid).order_by(Email.sent_at))).scalars().all()
        )

        documents = (await db.execute(select(Document).where(Document.company_id == cid))).scalars().all()

        servers = (await db.execute(select(Server).where(Server.company_id == cid))).scalars().all()

        infra = {
            "servers": [_row_dict(r, ["hostname", "ip", "role", "os", "services"]) for r in servers],
            "network_devices": await _all_rows(db, NetworkDevice, cid, ["hostname", "device_type", "vendor", "mgmt_ip"]),
            "subnets": await _all_rows(db, Subnet, cid, ["name", "cidr", "vlan_id"]),
            "cloud_infra": await _all_rows(db, CloudInfra, cid, ["provider", "account_id", "resources"]),
            "dns_records": await _all_rows(db, DnsRecord, cid, ["name", "record_type", "value", "ttl"]),
            "load_balancers": await _all_rows(db, LoadBalancer, cid, ["hostname", "lb_type", "ip", "upstream_pool"]),
            "ssl_certs": await _all_rows(
                db,
                SslCert,
                cid,
                ["hostname", "issuer", "subject", "valid_from", "valid_to", "self_signed", "weak_cipher"],
            ),
            "active_alerts": await _all_rows(
                db, ActiveAlert, cid, ["source", "alert_type", "message", "severity", "affected_host"]
            ),
            "ci_cd_pipelines": await _all_rows(
                db, CiCdPipeline, cid, ["name", "platform", "url", "misconfigurations"]
            ),
            "source_leaks": await _all_rows(
                db, SourceLeak, cid, ["platform", "url", "repo_name", "leaked_content", "exposure_date", "severity"]
            ),
            "container_registries": await _all_rows(db, ContainerRegistry, cid, ["registry_url", "provider"]),
            "terraform_states": await _all_rows(
                db, TerraformState, cid, ["backend_type", "state_file_url", "resources", "exposed_secrets"]
            ),
            "firewall_rules": await _all_rows(
                db, FirewallRule, cid, ["source", "destination", "port", "protocol", "action", "purpose"]
            ),
            "patch_gaps": await _all_rows(db, PatchGap, cid, ["hostname", "missing_patch", "severity"]),
            "service_accounts": await _all_rows(db, ServiceAccount, cid, ["username", "privilege_level", "used_by"]),
            "vpn_configs": await _all_rows(db, VpnConfig, cid, ["provider", "endpoint", "auth_method"]),
            "attack_artifacts": await _all_rows(
                db,
                AttackArtifact,
                cid,
                ["artifact_type", "name", "location", "content_excerpt", "severity", "description"],
            ),
        }

        return {
            **_company_summary(company, request),
            "employees": [_employee_dict(e) for e in employees],
            "emails": [_email_dict(e, request) for e in emails],
            "documents": [_document_dict(d) for d in documents],
            **infra,
        }


def _profile_dict(p, request: Request | None = None) -> dict:
    tz = get_user_tz(request) if request else None
    return {
        "id": str(p.id),
        "name": p.name,
        "industry": p.industry,
        "size": p.size,
        "company_name": p.company_name,
        "description": p.description,
        "location": p.location,
        "technologies": p.technologies if isinstance(p.technologies, list) else None,
        "security_posture": p.security_posture or "default",
        "created_at": format_dt(p.created_at, tz),
        "updated_at": format_dt(p.updated_at, tz),
    }


def _company_summary(c, request: Request | None = None) -> dict:
    tz = get_user_tz(request) if request else None
    return {
        "id": str(c.id),
        "user_id": str(c.user_id) if c.user_id else None,
        "name": c.name,
        "industry": c.industry,
        "size": c.size,
        "description": c.description,
        "location_city": c.location_city,
        "location_country": c.location_country,
        "founded_year": c.founded_year,
        "org_chart": c.org_chart,
        "status": c.status,
        "created_at": format_dt(c.created_at, tz),
        "updated_at": format_dt(c.updated_at, tz),
    }


def _employee_dict(e) -> dict:
    return {
        "id": str(e.id),
        "first_name": e.first_name,
        "last_name": e.last_name,
        "email": e.email,
        "title": e.title,
        "department": e.department,
        "manager_id": str(e.manager_id) if e.manager_id else None,
        "bio": e.bio,
        "skills": e.skills,
        "personality": e.personality,
    }


def _email_dict(e, request: Request | None = None) -> dict:
    tz = get_user_tz(request) if request else None
    return {
        "id": str(e.id),
        "thread_id": str(e.thread_id) if e.thread_id else None,
        "sender_id": str(e.sender_id),
        "recipient_ids": e.recipient_ids,
        "subject": e.subject,
        "body": e.body,
        "sent_at": format_dt(e.sent_at, tz),
        "is_internal": e.is_internal,
    }


def _document_dict(d) -> dict:
    return {
        "id": str(d.id),
        "author_id": str(d.author_id) if d.author_id else None,
        "title": d.title,
        "doc_type": d.doc_type,
        "content": d.content,
        "file_path": d.file_path,
    }


def _row_dict(obj, fields: list[str]) -> dict:
    out = {"id": str(obj.id)}
    for f in fields:
        v = getattr(obj, f, None)
        out[f] = str(v) if isinstance(v, uuid.UUID) else v
    return out


async def _all_rows(db, model, company_id: uuid.UUID, fields: list[str]) -> list[dict]:
    rows = (await db.execute(select(model).where(model.company_id == company_id))).scalars().all()
    return [_row_dict(r, fields) for r in rows]
