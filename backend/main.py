import asyncio
import json
import logging
import os
import signal
import time
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

from backend.ai.factory import init_providers
from backend.api.admin import router as admin_router
from backend.api.auth import router as auth_router
from backend.api.company import router as company_router
from backend.api.deploy import router as deploy_router
from backend.api.events import router as events_router
from backend.api.graph import router as graph_router
from backend.api.logs import router as logs_router
from backend.api.logs import set_log_handler
from backend.api.sessions import router as sessions_router
from backend.api.stats import router as stats_router
from backend.api.threats import router as threats_router
from backend.auth import validate_jwt_config, validate_required_config
from backend.database import close_db, get_session, get_session_maker, init_db
from backend.neo4j_client import close_neo4j, init_neo4j
from backend.services.json_formatter import JSONFormatter
from backend.services.log_handler import AsyncDBLogHandler
from backend.services.metrics import MetricsMiddleware, collect_task_metrics
from backend.services.seed_data import seed_events
from backend.services.task_manager import seed_default_tasks, task_manager
from backend.utils.config import Config
from backend.utils.timezone import get_user_tz

# Track startup time for health check
_startup_time: float = 0.0

# Context variable for request_id propagation
_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="unknown")


class RequestIDLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_ctx.get()
        return True

logger = logging.getLogger("shadowhive")

def _setup_logging() -> None:
    cfg = Config.load()
    log_level = getattr(logging, cfg.get("logging.level", "INFO").upper(), logging.INFO)
    log_format = cfg.get("logging.format", "json")
    if log_format == "json":
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        logging.basicConfig(level=log_level, handlers=[handler])
    else:
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
    logging.getLogger().addFilter(RequestIDLogFilter())

_setup_logging()


def _parse_cowrie_timestamp(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        ts = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        return dt.replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


def _get_deployed_company_id() -> uuid.UUID | None:
    """Read the active deployment marker to get the real company_id."""
    honeypot_dir = os.environ.get("HONEYPOT_DATA_DIR", "/app/honeypot_data")
    marker_path = Path(honeypot_dir) / "active_company.json"
    if not marker_path.exists():
        return None
    try:
        data = json.loads(marker_path.read_text())
        cid = data.get("company_id")
        if cid:
            return uuid.UUID(cid)
    except (json.JSONDecodeError, OSError, ValueError):
        logger.warning("Failed to read active_company.json for deployment-aware ingestion")
    return None


async def _cowrie_ingestion_loop(cfg: dict, shutdown: asyncio.Event):
    cowrie_cfg = cfg.get("ingestion", {}).get("cowrie", {})
    if not cowrie_cfg.get("enabled", True):
        return

    from backend.ingestion.cowrie_client import CowrieClient
    from backend.ingestion.honeypot_watcher import HoneypotFileWatcher
    from backend.models.company import AttackerEvent
    from backend.services.mitre_mapper import rule_based_match

    client = CowrieClient()
    poll_interval = cowrie_cfg.get("poll_interval", 30)
    fetch_limit = cowrie_cfg.get("fetch_limit", 100)
    last_since: str | None = None

    logger.info(f"Cowrie ingestion started — watching {client.log_path} every {poll_interval}s")

    # ── Additional honeypot watchers ─────────────────────────────────
    honeypot_log_dir = "/app/honeypot_logs"
    log_sources: list[dict] = [
        {"path": f"{honeypot_log_dir}/opencanary.json", "source": "opencanary", "poll": 15},
        {"path": f"{honeypot_log_dir}/portal_honeypot.json", "source": "portal", "poll": 10},
        {"path": f"{honeypot_log_dir}/wordpress.json", "source": "wordpress", "poll": 30},
        {"path": f"{honeypot_log_dir}/cowrie2.json", "source": "cowrie2", "poll": 30},
        {"path": f"{honeypot_log_dir}/cowrie3.json", "source": "cowrie3", "poll": 30},
    ]

    watchers: list[dict] = []
    for src in log_sources:
        watchers.append({
            "watcher": HoneypotFileWatcher(log_path=src["path"], source=src["source"]),
            "source": src["source"],
            "poll_interval": src["poll"],
            "last_since": None,
            "timer": 0,
        })
    logger.info(f"Registered {len(watchers)} additional honeypot log watchers")

    while not shutdown.is_set():
        try:
            events = await client.fetch_events(since=last_since, limit=fetch_limit)
            if events:
                async for db in get_session():
                    ingested = 0
                    for raw in events:
                        parsed = CowrieClient.parse_event(raw)
                        mitre = rule_based_match(
                            event_type=parsed.get("event_type", ""),
                            command=parsed.get("command", ""),
                        )
                        event = AttackerEvent(
                            id=uuid.uuid4(),
                            user_id=None,
                            company_id=_get_deployed_company_id() or uuid.uuid4(),
                            source_ip=parsed.get("source_ip", "unknown"),
                            event_type=parsed.get("event_type", "unknown"),
                            command=parsed.get("command") or None,
                            session_id=parsed.get("session_id"),
                            mitre_technique_id=mitre["technique_id"] if mitre else None,
                            mitre_tactic=mitre["tactic"] if mitre else None,
                            confidence_score=str(mitre["confidence"]) if mitre else None,
                            detected_at=(_parse_cowrie_timestamp(parsed.get("timestamp")) or datetime.now(UTC).replace(tzinfo=None)),
                        )
                        db.add(event)
                        ingested += 1
                    await db.commit()
                    if ingested:
                        logger.info(f"Ingested {ingested} Cowrie events")
                        last_ts = events[-1].get("timestamp")
                        if last_ts:
                            last_since = last_ts
        except Exception as e:
            logger.warning(f"Cowrie poll failed: {e}")

        # ── Poll additional honeypot watchers ────────────────────────
        for w in watchers:
            w["timer"] += poll_interval
            if w["timer"] < w["poll_interval"]:
                continue
            w["timer"] = 0
            try:
                extra_events = await w["watcher"].fetch_events(since=w["last_since"], limit=fetch_limit)
                if extra_events:
                    async for db in get_session():
                        ingested = 0
                        for raw in extra_events:
                            parsed = _parse_honeypot_event(raw, w["source"])
                            mitre = rule_based_match(
                                event_type=parsed.get("event_type", ""),
                                command=parsed.get("command", ""),
                            )
                            event = AttackerEvent(
                                id=uuid.uuid4(),
                                user_id=None,
                                company_id=_get_deployed_company_id() or uuid.uuid4(),
                                source_ip=parsed.get("source_ip", "unknown"),
                                event_type=parsed.get("event_type", "unknown"),
                                command=parsed.get("command") or None,
                                session_id=parsed.get("session_id"),
                                mitre_technique_id=mitre["technique_id"] if mitre else None,
                                mitre_tactic=mitre["tactic"] if mitre else None,
                                confidence_score=str(mitre["confidence"]) if mitre else None,
                                detected_at=parsed.get("detected_at") or datetime.now(UTC).replace(tzinfo=None),
                            )
                            db.add(event)
                            ingested += 1
                        await db.commit()
                        if ingested:
                            logger.info(f"Ingested {ingested} events from {w['source']}")
                            last_ts = extra_events[-1].get("timestamp") or extra_events[-1].get("_time", "")
                            if last_ts:
                                w["last_since"] = last_ts
            except Exception as e:
                logger.warning(f"{w['source']} poll failed: {e}")

        try:
            await asyncio.wait_for(shutdown.wait(), timeout=poll_interval)
        except TimeoutError:
            pass


def _parse_honeypot_event(raw: dict, source: str) -> dict:
    """Normalize events from various honeypot sources into a common format."""
    ts = raw.get("timestamp") or raw.get("_time") or raw.get("log_time") or ""
    if ts:
        try:
            ts_stripped = ts.replace("Z", "+00:00")
            detected_at = datetime.fromisoformat(ts_stripped).replace(tzinfo=None)
        except (ValueError, TypeError):
            detected_at = datetime.now(UTC).replace(tzinfo=None)
    else:
        detected_at = datetime.now(UTC).replace(tzinfo=None)

    if source == "opencanary":
        return {
            "source_ip": raw.get("remote_host", raw.get("src_ip", raw.get("source_ip", "unknown"))),
            "event_type": f"opencanary.{raw.get('event_type', raw.get('logtype', 'unknown'))}",
            "command": raw.get("message", raw.get("input", raw.get("data", ""))),
            "session_id": raw.get("session", raw.get("conversation_id", "")),
            "detected_at": detected_at,
        }
    elif source == "portal":
        return {
            "source_ip": raw.get("source_ip", raw.get("remote_addr", "unknown")),
            "event_type": f"web.{raw.get('event_type', 'credential_harvest')}",
            "command": raw.get("path", raw.get("url", "")),
            "session_id": raw.get("session_id", raw.get("conversation_id", "")),
            "detected_at": detected_at,
        }
    elif source in ("cowrie2", "cowrie3"):
        return {
            "source_ip": raw.get("src_ip", "unknown"),
            "event_type": raw.get("eventid", "unknown"),
            "command": raw.get("message", raw.get("input", "")),
            "session_id": raw.get("session", ""),
            "detected_at": detected_at,
        }
    elif source == "dionaea":
        return {
            "source_ip": raw.get("remote_host", raw.get("src_ip", "unknown")),
            "event_type": f"dionaea.{raw.get('event_type', raw.get('logtype', 'unknown'))}",
            "command": raw.get("message", raw.get("input", raw.get("data", ""))),
            "session_id": raw.get("session", raw.get("conversation_id", "")),
            "detected_at": detected_at,
        }
    elif source == "wordpress":
        return {
            "source_ip": raw.get("remote_addr", raw.get("source_ip", "unknown")),
            "event_type": f"wp.{raw.get('event_type', 'login_attempt')}",
            "command": raw.get("request", raw.get("uri", "")),
            "session_id": raw.get("session", ""),
            "detected_at": detected_at,
        }
    else:
        return {
            "source_ip": raw.get("source_ip", raw.get("src_ip", "unknown")),
            "event_type": raw.get("event_type", f"{source}.unknown"),
            "command": raw.get("command", raw.get("message", "")),
            "session_id": raw.get("session_id", ""),
            "detected_at": detected_at,
        }


_SHUTDOWN_TIMEOUT = 30  # seconds


def _handle_signal(sig: int, frame):
    sig_name = signal.Signals(sig).name
    logger.info(f"Received {sig_name}, initiating graceful shutdown...")
    raise SystemExit(0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _startup_time

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    cfg = Config.load()
    shutdown_event = asyncio.Event()
    cowrie_task = None
    _startup_time = time.time()

    logger.info("ShadowHive starting up...")

    for warning in validate_jwt_config() + validate_required_config():
        logger.warning(warning)

    init_providers(cfg.get("ai", {}))
    log_handler = None
    try:
        await init_db()
        logger.info("PostgreSQL connected")
        try:
            sm = get_session_maker()
            if sm:
                await task_manager.set_session_factory(sm)
                logger.info("Task manager recovered orphaned tasks from DB")
                log_handler = AsyncDBLogHandler(sm)
                log_handler.setLevel(logging.INFO)
                root_logger = logging.getLogger()
                root_logger.addHandler(log_handler)
                await log_handler.start()
                set_log_handler(log_handler)
                logger.info("Async DB log handler attached")
        except Exception as e:
            logger.warning(f"Task manager/Log handler init failed: {e}")
    except Exception as e:
        logger.warning(f"PostgreSQL not available: {e}")
    try:
        await init_neo4j()
        logger.info("Neo4j connected")
    except Exception as e:
        logger.warning(f"Neo4j not available: {e}")
    try:
        await seed_default_tasks()
        logger.info("Seeded default company tasks")
    except Exception as e:
        logger.warning(f"Failed to seed company tasks: {e}")
    try:
        from backend.api.auth import ensure_admin_exists

        await ensure_admin_exists()
        logger.info("Default admin account ensured")
    except Exception as e:
        logger.warning(f"Failed to ensure admin: {e}")
    try:
        await seed_events()
        logger.info("Seeded event data")
    except Exception as e:
        logger.warning(f"Failed to seed events: {e}")

    cowrie_task = asyncio.create_task(_cowrie_ingestion_loop(cfg, shutdown_event))

    async def _metrics_loop():
        while not shutdown_event.is_set():
            await collect_task_metrics()
            await asyncio.sleep(15)

    metrics_task = asyncio.create_task(_metrics_loop())

    yield

    metrics_task.cancel()
    try:
        await asyncio.wait_for(metrics_task, timeout=3)
    except (TimeoutError, asyncio.CancelledError):
        pass

    logger.info("Shutting down gracefully...")
    shutdown_event.set()

    # Drain in-flight task manager tasks
    running = [t for t in task_manager._tasks.values() if t.status == "running"]
    if running:
        logger.info(f"Draining {len(running)} in-flight tasks...")
        for t in running:
            t.cancel()

    # Drain log buffer
    if log_handler:
        await log_handler.stop()

    # Cancel cowrie polling
    if cowrie_task:
        cowrie_task.cancel()
        try:
            await asyncio.wait_for(cowrie_task, timeout=5)
        except (TimeoutError, asyncio.CancelledError):
            pass

    # Close DB connections with timeout
    try:
        await asyncio.wait_for(close_db(), timeout=10)
    except TimeoutError:
        logger.warning("Database close timed out")
    try:
        await asyncio.wait_for(close_neo4j(), timeout=5)
    except TimeoutError:
        logger.warning("Neo4j close timed out")

    logger.info("ShadowHive shut down")


app = FastAPI(
    title="ShadowHive API",
    description="Autonomous Deception and Adversary Intelligence Platform",
    version="0.1.0",
    lifespan=lifespan,
)

class TimezoneMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.user_tz = get_user_tz(request)
        return await call_next(request)


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = rid
        token = _request_id_ctx.set(rid)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            _request_id_ctx.reset(token)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'none'; frame-ancestors 'none'"
        )
        return response


app.add_middleware(TimezoneMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(MetricsMiddleware)

cors_methods = (
    ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
    if not Config.get("server.debug", True)
    else ["*"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=Config.get("server.cors_origins", ["http://localhost:3000"]),
    allow_credentials=True,
    allow_methods=cors_methods,
    allow_headers=["*"],
)

app.include_router(company_router)
app.include_router(stats_router)
app.include_router(threats_router)
app.include_router(sessions_router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(events_router)
app.include_router(deploy_router)
app.include_router(graph_router)
app.include_router(logs_router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    rid = getattr(request.state, "request_id", "unknown")
    logger.error(
        f"Unhandled exception on {request.method} {request.url.path}",
        exc_info=True,
        extra={"request_id": rid},
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error", "request_id": rid})


@app.get("/")
async def root():
    uptime = time.time() - _startup_time if _startup_time else 0
    return {
        "service": "ShadowHive",
        "version": "0.1.0",
        "status": "running",
        "uptime_seconds": round(uptime),
    }


@app.get("/metrics")
async def metrics():
    await collect_task_metrics()
    return Response(content=generate_latest().decode("utf-8"), media_type="text/plain")


@app.get("/health")
async def health():
    from backend.database import _engine as db_engine
    from backend.neo4j_client import _driver as neo4j_driver

    db_ok = db_engine is not None
    neo4j_ok = neo4j_driver is not None
    ai_ok = True
    try:
        from backend.ai.factory import _providers
        ai_ok = len(_providers) > 0
    except Exception:
        ai_ok = False

    status_code = 200 if db_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if db_ok else "degraded",
            "checks": {
                "database": "ok" if db_ok else "unavailable",
                "neo4j": "ok" if neo4j_ok else "unavailable",
                "ai_providers": "ok" if ai_ok else "unavailable",
            },
            "uptime_seconds": round(time.time() - _startup_time) if _startup_time else 0,
        },
    )
