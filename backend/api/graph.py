from fastapi import APIRouter, Depends, Query

from backend.auth import get_optional_user
from backend.models.user import User
from backend.neo4j_client import _driver as neo4j_driver
from backend.services.graph_builder import get_attack_paths, get_ip_summary, get_technique_summary

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get("/attack-paths")
async def attack_paths(
    limit: int = Query(50, le=200),
    _user: User | None = Depends(get_optional_user),
):
    if not neo4j_driver:
        return {"paths": [], "message": "Neo4j not available"}
    async with neo4j_driver.session() as session:
        paths = await get_attack_paths(session, limit=limit)
    return {"paths": paths, "count": len(paths)}


@router.get("/techniques")
async def technique_summary(
    _user: User | None = Depends(get_optional_user),
):
    if not neo4j_driver:
        return {"techniques": [], "message": "Neo4j not available"}
    async with neo4j_driver.session() as session:
        techniques = await get_technique_summary(session)
    return {"techniques": techniques}


@router.get("/ips")
async def ip_summary(
    limit: int = Query(20, le=100),
    _user: User | None = Depends(get_optional_user),
):
    if not neo4j_driver:
        return {"ips": [], "message": "Neo4j not available"}
    async with neo4j_driver.session() as session:
        ips = await get_ip_summary(session, limit=limit)
    return {"ips": ips}
