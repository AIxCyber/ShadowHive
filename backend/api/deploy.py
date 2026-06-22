import uuid

from fastapi import APIRouter, Depends, HTTPException

from backend.auth import get_current_user, is_auth_enabled
from backend.database import get_session
from backend.models.company import Company
from backend.models.user import User
from backend.services.honeypot_deployer import (
    deploy_company,
    get_deployment_status,
    undeploy_company,
)

router = APIRouter(prefix="/api/deploy", tags=["deploy"])


@router.post("/undeploy")
async def undeploy(user: User = Depends(get_current_user)):
    if is_auth_enabled() and not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return await undeploy_company()


@router.post("/{company_id}")
async def deploy(company_id: uuid.UUID, user: User = Depends(get_current_user)):
    if is_auth_enabled() and not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    async for db in get_session():
        company = await db.get(Company, company_id)
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        existing = await get_deployment_status()
        result = await deploy_company(db, company_id)

        if existing.get("active") and existing.get("company_id") != str(company_id):
            result["previous_deployment"] = existing.get("company_name")
            result["warning"] = f"Overwrote previous deployment of '{existing.get('company_name')}'"

        return result


@router.get("/status")
async def status(user: User | None = Depends(get_current_user)):
    return await get_deployment_status()
