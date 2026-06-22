import asyncio
import logging
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


def _naive_utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Task:
    def __init__(self, task_type: str, params: dict[str, Any], user_id: str | None = None):
        self.id = str(uuid.uuid4())
        self.type = task_type
        self.params = params
        self.user_id = user_id
        self.status = TaskStatus.PENDING
        self.progress = 0.0
        self.message = "Queued"
        self.result: Any | None = None
        self.error: str | None = None
        self.created_at = _naive_utcnow()
        self.started_at: datetime | None = None
        self.completed_at: datetime | None = None
        self._coro: asyncio.Task | None = None
        self._paused = asyncio.Event()
        self._paused.set()

    def to_dict(self) -> dict:
        status_val = self.status.value if isinstance(self.status, TaskStatus) else self.status
        return {
            "task_id": self.id,
            "type": self.type,
            "status": status_val,
            "progress": self.progress,
            "message": self.message,
            "error": self.error,
            "result": self.result,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat() + "Z",
            "started_at": self.started_at.isoformat() + "Z" if self.started_at else None,
            "completed_at": self.completed_at.isoformat() + "Z" if self.completed_at else None,
        }


class TaskManager:
    def __init__(self):
        self._tasks: dict[str, Task] = {}
        self._lock = asyncio.Lock()
        self._session_maker = None

    async def set_session_factory(self, session_maker):
        self._session_maker = session_maker
        from sqlalchemy import select, update

        from backend.models.company import GenerationTask

        async with self._lock:
            async with session_maker() as session:
                result = await session.execute(
                    select(GenerationTask).where(GenerationTask.status.in_(["pending", "running", "paused"]))
                )
                for row in result.scalars().all():
                    task = Task(row.type, row.params or {}, user_id=row.user_id)
                    task.id = row.task_id
                    task.status = TaskStatus(row.status)
                    task.progress = row.progress
                    task.message = row.message or "Queued"
                    task.error = row.error
                    task.result = row.result
                    task.created_at = row.created_at
                    task.started_at = row.started_at
                    task.completed_at = row.completed_at
                    if task.status in (TaskStatus.RUNNING, TaskStatus.PAUSED):
                        task.status = TaskStatus.FAILED
                        task.error = "Generation interrupted by server restart"
                        await session.execute(
                            update(GenerationTask)
                            .where(GenerationTask.task_id == task.id)
                            .values(status="failed", error="Generation interrupted by server restart")
                        )
                    self._tasks[task.id] = task
                await session.commit()

    async def _persist(self, task: Task):
        from sqlalchemy import select

        from backend.models.company import GenerationTask

        if not self._session_maker:
            return
        try:
            async with self._session_maker() as session:
                result = await session.execute(select(GenerationTask).where(GenerationTask.task_id == task.id))
                db_task = result.scalar_one_or_none()
                if db_task:
                    db_task.type = task.type
                    db_task.params = task.params
                    db_task.user_id = task.user_id
                    db_task.status = task.status.value if isinstance(task.status, TaskStatus) else task.status
                    db_task.progress = task.progress
                    db_task.message = task.message
                    db_task.error = task.error
                    db_task.result = task.result
                    db_task.started_at = task.started_at
                    db_task.completed_at = task.completed_at
                else:
                    session.add(
                        GenerationTask(
                            task_id=task.id,
                            user_id=task.user_id,
                            type=task.type,
                            params=task.params,
                            status=task.status.value if isinstance(task.status, TaskStatus) else task.status,
                            progress=task.progress,
                            message=task.message,
                            error=task.error,
                            result=task.result,
                            started_at=task.started_at,
                            created_at=task.created_at,
                            completed_at=task.completed_at,
                        )
                    )
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to persist task {task.id}: {type(e).__name__}: {e}", exc_info=True)

    async def _remove_from_db(self, task_id: str):
        from sqlalchemy import delete as sa_delete

        from backend.models.company import GenerationTask

        if not self._session_maker:
            return
        async with self._session_maker() as session:
            await session.execute(sa_delete(GenerationTask).where(GenerationTask.task_id == task_id))
            await session.commit()

    async def create(self, task_type: str, params: dict[str, Any], user_id: str | None = None) -> Task:
        async with self._lock:
            task = Task(task_type, params, user_id=user_id)
            self._tasks[task.id] = task
            logger.info("CREATE task %s status=%s _tasks_size=%d", task.id[:8], task.status.value, len(self._tasks))
        await self._persist(task)
        return task

    async def update(self, task_id: str, **kwargs):
        async with self._lock:
            task = self._tasks.get(task_id)
            if task:
                for k, v in kwargs.items():
                    if k == "status" and isinstance(v, str):
                        try:
                            v = TaskStatus(v)
                        except ValueError:
                            pass
                    setattr(task, k, v)
                if task.status == TaskStatus.RUNNING and task.started_at is None:
                    task.started_at = _naive_utcnow()
                logger.info(
                    "UPDATE task %s -> status=%s _tasks_size=%d",
                    task_id[:8],
                    task.status.value if isinstance(task.status, TaskStatus) else task.status,
                    len(self._tasks),
                )
            else:
                logger.warning("UPDATE task %s NOT FOUND in _tasks (_tasks_size=%d)", task_id[:8], len(self._tasks))
        if task:
            await self._persist(task)

    async def get(self, task_id: str) -> Task | None:
        task = self._tasks.get(task_id)
        if task:
            return task
        logger.warning(
            "GET task %s NOT FOUND in _tasks (_tasks_size=%d, _tasks_keys=%s)",
            task_id[:8],
            len(self._tasks),
            list(self._tasks.keys())[:5],
        )
        from sqlalchemy import select

        from backend.models.company import GenerationTask

        if not self._session_maker:
            return None
        async with self._session_maker() as session:
            result = await session.execute(select(GenerationTask).where(GenerationTask.task_id == task_id))
            row = result.scalar_one_or_none()
            if not row:
                return None
            t = Task(row.type, row.params or {}, user_id=row.user_id)
            t.id = row.task_id
            t.status = TaskStatus(row.status)
            t.progress = row.progress
            t.message = row.message or "Queued"
            t.error = row.error
            t.result = row.result
            t.created_at = row.created_at
            t.started_at = row.started_at
            t.completed_at = row.completed_at
            self._tasks[t.id] = t
            return t

    async def list_tasks(self, limit: int = 20) -> list[Task]:
        tasks = sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)
        if tasks or not self._session_maker:
            return tasks[:limit]
        from sqlalchemy import select

        from backend.models.company import GenerationTask

        async with self._session_maker() as session:
            result = await session.execute(
                select(GenerationTask).order_by(GenerationTask.created_at.desc()).limit(limit)
            )
            for row in result.scalars().all():
                if row.task_id in self._tasks:
                    continue
                t = Task(row.type, row.params or {}, user_id=row.user_id)
                t.id = row.task_id
                t.status = TaskStatus(row.status)
                t.progress = row.progress
                t.message = row.message or "Queued"
                t.error = row.error
                t.result = row.result
                t.created_at = row.created_at
                t.started_at = row.started_at
                t.completed_at = row.completed_at
                self._tasks[t.id] = t
        tasks = sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)
        return tasks[:limit]

    def register(self, task_id: str, coro):
        task = self._tasks.get(task_id)
        if task:
            task._coro = asyncio.create_task(coro)
            task._coro.add_done_callback(lambda _: asyncio.create_task(self._on_done(task_id)))

    async def pause(self, task_id: str):
        async with self._lock:
            task = self._tasks.get(task_id)
            if task and task.status == TaskStatus.RUNNING:
                task.status = TaskStatus.PAUSED
                task._paused.clear()
        if task:
            await self._persist(task)

    async def resume(self, task_id: str):
        async with self._lock:
            task = self._tasks.get(task_id)
            if task and task.status == TaskStatus.PAUSED:
                task.status = TaskStatus.RUNNING
                task._paused.set()
        if task:
            await self._persist(task)

    async def cancel(self, task_id: str):
        async with self._lock:
            task = self._tasks.get(task_id)
            if task and task.status in (TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.PAUSED):
                task.status = TaskStatus.CANCELLED
                task._paused.set()
                if task._coro:
                    task._coro.cancel()
        if task:
            await self._persist(task)

    async def delete(self, task_id: str):
        async with self._lock:
            self._tasks.pop(task_id, None)
        await self._remove_from_db(task_id)

    async def _on_done(self, task_id: str):
        task = self._tasks.get(task_id)
        if not task:
            return
        if task._coro and task._coro.exception():
            exc = task._coro.exception()
            if isinstance(exc, asyncio.CancelledError):
                await self.update(task_id, status="cancelled", message="Cancelled", completed_at=_naive_utcnow())
            else:
                await self.update(
                    task_id, status="failed", error=f"{type(exc).__name__}: {exc}", completed_at=_naive_utcnow()
                )


task_manager = TaskManager()


SEED_COMPANIES = [
    {
        "name": "NexGen Dynamics",
        "industry": "Technology",
        "size": "medium",
        "location": "San Francisco, CA",
        "description": "A cutting-edge AI research lab specializing in autonomous systems and neural network architectures. Known for their innovative approach to machine learning pipeline automation.",
        "founded_year": 2019,
        "revenue": "$45M",
        "employees": [
            {"name": "Dr. Sarah Chen", "title": "Chief AI Officer", "department": "Executive"},
            {"name": "Marcus Webb", "title": "Head of Engineering", "department": "Engineering"},
            {"name": "Elena Rodriguez", "title": "ML Research Lead", "department": "Research"},
            {"name": "James Kim", "title": "DevOps Engineer", "department": "Infrastructure"},
            {"name": "Lisa Patel", "title": "Security Analyst", "department": "Security"},
        ],
        "emails": [
            {
                "from": "sarah.chen@nexgendynamics.io",
                "to": "team@nexgendynamics.io",
                "subject": "Q3 Model Deployment Pipeline Review",
                "body": "Team, please review the updated deployment pipeline for our flagship recommendation engine. We need to ensure compliance with the new data residency requirements before the October rollout. Key changes include: (1) Multi-region model sharding, (2) Enhanced audit logging, (3) Automated rollback triggers.",
            },
            {
                "from": "elena.rodriguez@nexgendynamics.io",
                "to": "sarah.chen@nexgendynamics.io",
                "subject": "Re: Research Compute Budget Allocation",
                "body": "Sarah, I've revised the compute budget request for the LLM fine-tuning project. We can reduce costs by 30% using spot instances with checkpointing. The trade-off is increased training time from 2 to 3 weeks. Let me know if you want to proceed with this approach.",
            },
        ],
        "documents": [
            {
                "title": "Infrastructure Security Audit 2024",
                "type": "Security Report",
                "risk_level": "confidential",
                "content": "NexGen Dynamics operates 47 production servers across 3 cloud providers. Audit findings: 2 critical CVEs in web-facing services, 12 medium-severity configuration issues. Recommended actions: Patch CVE-2024-27198 on all API gateways within 48 hours.",
            },
            {
                "title": "Q2 Board Meeting Minutes",
                "type": "Minutes",
                "risk_level": "internal",
                "content": "Topics discussed: 1. Series B funding at $200M valuation 2. New partnership with DefenseTech Corp 3. Expansion to EU market requiring GDPR compliance team 4. Departure of CISO effective August 1st.",
            },
        ],
        "infrastructure": {
            "domain": "nexgendynamics.internal",
            "servers": [
                {
                    "hostname": "WEB-01",
                    "ip": "10.10.1.10",
                    "role": "Web Server",
                    "os": "Ubuntu 22.04",
                    "services": ["nginx/1.24", "node/20"],
                },
                {
                    "hostname": "API-01",
                    "ip": "10.10.1.11",
                    "role": "API Gateway",
                    "os": "Ubuntu 22.04",
                    "services": ["kong/3.6", "postgres/15"],
                },
                {
                    "hostname": "ML-01",
                    "ip": "10.10.2.10",
                    "role": "ML Training",
                    "os": "Ubuntu 22.04",
                    "services": ["nvidia-driver/545", "docker/24", "k8s/1.28"],
                },
                {
                    "hostname": "DB-01",
                    "ip": "10.10.3.10",
                    "role": "Database",
                    "os": "Ubuntu 22.04",
                    "services": ["postgres/15", "redis/7"],
                },
                {
                    "hostname": "DC-01",
                    "ip": "10.10.0.10",
                    "role": "Domain Controller",
                    "os": "Windows Server 2022",
                    "services": ["AD", "DNS", "DHCP"],
                },
                {
                    "hostname": "MON-01",
                    "ip": "10.10.0.20",
                    "role": "Monitoring",
                    "os": "Ubuntu 22.04",
                    "services": ["prometheus/2.50", "grafana/10"],
                },
            ],
            "network_devices": [
                {"hostname": "fw-01", "type": "firewall", "vendor": "pfSense", "mgmt_ip": "10.10.255.1"},
                {"hostname": "sw-core-01", "type": "switch", "vendor": "Cisco", "mgmt_ip": "10.10.255.2"},
                {"hostname": "sw-access-01", "type": "switch", "vendor": "Cisco", "mgmt_ip": "10.10.255.10"},
                {"hostname": "ap-01", "type": "AP", "vendor": "Ubiquiti", "mgmt_ip": "10.10.255.20"},
            ],
            "subnets": [
                {"name": "Management", "cidr": "10.10.0.0/24", "vlan_id": 10},
                {"name": "Web", "cidr": "10.10.1.0/24", "vlan_id": 20},
                {"name": "ML Cluster", "cidr": "10.10.2.0/24", "vlan_id": 30},
                {"name": "Database", "cidr": "10.10.3.0/24", "vlan_id": 40},
            ],
            "cloud_infra": {
                "provider": "AWS",
                "account_id": "123456789012",
                "resources": ["S3: ml-models-bucket", "RDS: aurora-prod-01", "EKS: k8s-cluster-prod"],
            },
        },
        "network_depth": {
            "dns_records": [
                {"name": "nexgendynamics.internal", "type": "A", "value": "10.10.1.10", "ttl": 3600},
                {"name": "api.nexgendynamics.internal", "type": "A", "value": "10.10.1.11", "ttl": 3600},
                {"name": "ml-cluster.nexgendynamics.internal", "type": "A", "value": "10.10.2.10", "ttl": 3600},
                {
                    "name": "db-primary.nexgendynamics.internal",
                    "type": "CNAME",
                    "value": "db-01.nexgendynamics.internal",
                    "ttl": 3600,
                },
                {"name": "monitor.nexgendynamics.internal", "type": "A", "value": "10.10.0.20", "ttl": 3600},
                {
                    "name": "mail.nexgendynamics.internal",
                    "type": "MX",
                    "value": "10 mail-proxy.nexgendynamics.internal",
                    "ttl": 3600,
                },
            ],
            "load_balancers": [
                {
                    "hostname": "lb-01",
                    "type": "nginx",
                    "ip": "10.10.1.5",
                    "upstream_pool": ["web-01:443"],
                    "listeners": [{"port": 443, "protocol": "HTTPS", "backend": "web-pool"}],
                },
            ],
            "ssl_certs": [
                {
                    "hostname": "*.nexgendynamics.internal",
                    "issuer": "Let's Encrypt",
                    "subject": "CN=*.nexgendynamics.internal",
                    "valid_from": "2024-06-01",
                    "valid_to": "2025-06-01",
                    "san": ["nexgendynamics.internal", "api.nexgendynamics.internal"],
                    "self_signed": False,
                    "weak_cipher": False,
                },
                {
                    "hostname": "dev-api.nexgendynamics.internal",
                    "issuer": "Self-Signed",
                    "subject": "CN=dev-api.nexgendynamics.internal",
                    "valid_from": "2023-01-01",
                    "valid_to": "2024-01-01",
                    "san": ["dev-api.nexgendynamics.internal"],
                    "self_signed": True,
                    "weak_cipher": True,
                },
            ],
            "active_alerts": [
                {
                    "source": "CrowdStrike",
                    "type": "EDR Detection",
                    "message": "Suspicious outbound connection from ML-01 to known C2 infrastructure (45.33.32.156:4443). Process: python3 spawned reverse shell.",
                    "severity": "critical",
                    "affected_host": "ML-01 (10.10.2.10)",
                    "timestamp": "2 min ago",
                },
                {
                    "source": "Snort",
                    "type": "IDS Alert",
                    "message": "ET MALWARE Possible Cobalt Strike Beacon Detected (JA3 hash match) — traffic from WEB-01 to external IP 185.220.101.42:8080",
                    "severity": "high",
                    "affected_host": "WEB-01 (10.10.1.10)",
                    "timestamp": "15 min ago",
                },
                {
                    "source": "pfSense",
                    "type": "Firewall Block",
                    "message": "Repeated SSH brute force attempts from 91.121.89.110 targeting DC-01 — 1,247 blocked attempts in the last hour",
                    "severity": "medium",
                    "affected_host": "DC-01 (10.10.0.10)",
                    "timestamp": "45 min ago",
                },
            ],
        },
        "security_config": {
            "firewall_rules": [
                {
                    "source": "0.0.0.0/0",
                    "destination": "WEB-01",
                    "port": "443",
                    "protocol": "TCP",
                    "action": "ALLOW",
                    "purpose": "Public HTTPS",
                },
                {
                    "source": "WEB-01",
                    "destination": "API-01",
                    "port": "3000",
                    "protocol": "TCP",
                    "action": "ALLOW",
                    "purpose": "API traffic from web tier",
                },
                {
                    "source": "API-01",
                    "destination": "DB-01",
                    "port": "5432",
                    "protocol": "TCP",
                    "action": "ALLOW",
                    "purpose": "Database queries",
                },
                {
                    "source": "10.10.0.0/24",
                    "destination": "Any",
                    "port": "22",
                    "protocol": "TCP",
                    "action": "ALLOW",
                    "purpose": "SSH from management subnet",
                },
                {
                    "source": "0.0.0.0/0",
                    "destination": "Any",
                    "port": "22",
                    "protocol": "TCP",
                    "action": "DENY",
                    "purpose": "Block external SSH",
                },
            ],
            "edr_status": "SentinelOne",
            "edr_coverage": "All servers except ML cluster",
            "patch_gaps": [
                {"hostname": "WEB-01", "missing_patch": "CVE-2024-27198", "severity": "Critical"},
                {"hostname": "ML-01", "missing_patch": "CVE-2024-6387", "severity": "Critical"},
            ],
            "service_accounts": [
                {"username": "svc_kong", "privilege_level": "Local Admin", "used_by": "Kong API Gateway"},
                {"username": "svc_ml_train", "privilege_level": "Domain Admin", "used_by": "ML Training Pipeline"},
            ],
            "vpn_config": {"provider": "WireGuard", "endpoint": "vpn.nexgendynamics.io", "auth_method": "Certificate"},
        },
        "attack_artifacts": [
            {
                "type": "config_file",
                "name": "kong_env_backup.yaml",
                "location": "/opt/kong/backups/kong_env_backup.yaml",
                "content_excerpt": "admin_api_key: 'sk_live_xxxxxxxxxxxxxxxxxxxxx'\ndb_password: 'P@ssw0rd!2024'",
                "severity": "high",
                "description": "Exposes Kong admin API key and database password for API gateway",
            },
            {
                "type": "ssh_key",
                "name": "ml-admin_id_rsa",
                "location": "/home/jkim/.ssh/ml-admin_id_rsa",
                "content_excerpt": "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAABFwAAAAdzc2gtcn\nNhAAAAAwEAAQAAAQEA6NFjx...",
                "severity": "critical",
                "description": "SSH private key for the ML cluster admin user — grants root access to all training nodes",
            },
        ],
        "devops_pipeline": {
            "ci_cd_pipelines": [
                {
                    "name": "ml-model-deploy",
                    "platform": "GitHub Actions",
                    "url": "https://github.com/nexgen-dynamics/ml-platform/.github/workflows/deploy.yml",
                    "misconfigurations": [
                        "AWS access keys stored as plaintext secrets in workflow YAML",
                        "No approval gate on production deployments",
                    ],
                    "jobs": [
                        {
                            "name": "test",
                            "stage": "Quality",
                            "script_summary": "pytest tests/ --cov=src --junitxml=results.xml",
                        },
                        {
                            "name": "build-image",
                            "stage": "Build",
                            "script_summary": "docker build -t ml-inference:${{ github.sha }} .",
                        },
                        {
                            "name": "push-ecr",
                            "stage": "Publish",
                            "script_summary": "aws ecr get-login-password | docker push $ECR_REPO/ml-inference:latest",
                        },
                        {
                            "name": "deploy-prod",
                            "stage": "Deploy",
                            "script_summary": "kubectl apply -f k8s/production/deployment.yaml --namespace=ml-prod",
                        },
                    ],
                },
                {
                    "name": "web-app-ci",
                    "platform": "GitHub Actions",
                    "url": "https://github.com/nexgen-dynamics/web-app/.github/workflows/ci.yml",
                    "misconfigurations": ["Node modules cached without integrity verification"],
                    "jobs": [
                        {"name": "lint", "stage": "Quality", "script_summary": "eslint src/ && prettier --check src/"},
                        {"name": "build", "stage": "Build", "script_summary": "npm ci && npm run build"},
                    ],
                },
            ],
            "source_leaks": [
                {
                    "platform": "GitHub",
                    "url": "https://github.com/jkim-nexgen/internal-tools",
                    "repo_name": "internal-tools",
                    "leaked_content": "AWS_ACCESS_KEY_ID=AKIA4ML7K9R2NQ3X5V8B\nAWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY\nMLFLOW_TRACKING_URI=http://ml-01:5000",
                    "exposure_date": "2024-03-12",
                    "severity": "critical",
                },
            ],
            "container_registries": [
                {
                    "registry_url": "123456789012.dkr.ecr.us-west-2.amazonaws.com",
                    "provider": "ECR",
                    "repositories": [
                        {
                            "name": "ml-inference",
                            "tags": ["latest", "v2.1.0", "v2.0.3"],
                            "vulnerability_count": 18,
                            "critical_vulns": 4,
                        },
                        {
                            "name": "web-app",
                            "tags": ["latest", "v1.8.2"],
                            "vulnerability_count": 7,
                            "critical_vulns": 1,
                        },
                        {
                            "name": "api-gateway",
                            "tags": ["latest", "v3.0.1"],
                            "vulnerability_count": 3,
                            "critical_vulns": 0,
                        },
                    ],
                },
            ],
            "terraform_state": {
                "backend_type": "S3",
                "state_file_url": "s3://nexgen-tf-state-prod/terraform.tfstate",
                "resources": [
                    "aws_eks_cluster.ml-platform",
                    "aws_s3_bucket.model_storage",
                    "aws_iam_access_key.cicd_deployer",
                    "aws_db_instance.aurora_prod",
                ],
                "exposed_secrets": ["AWS_SECRET_ACCESS_KEY (cicd_deployer)", "DB_MASTER_PASSWORD"],
            },
        },
    },
    {
        "name": "Meridian Financial",
        "industry": "Finance",
        "size": "large",
        "location": "New York, NY",
        "description": "A premier financial services firm offering wealth management, corporate banking, and algorithmic trading solutions to high-net-worth clients and institutional investors.",
        "founded_year": 2005,
        "revenue": "$890M",
        "employees": [
            {"name": "Robert Whitmore", "title": "CEO", "department": "Executive"},
            {"name": "Amanda Foster", "title": "CIO", "department": "IT"},
            {"name": "David Park", "title": "Head of Trading Systems", "department": "Trading"},
            {"name": "Jennifer Lopez", "title": "Compliance Officer", "department": "Legal"},
            {"name": "Michael Torres", "title": "Network Architect", "department": "Infrastructure"},
        ],
        "emails": [
            {
                "from": "amanda.foster@meridian-fin.com",
                "to": "david.park@meridian-fin.com",
                "subject": "Trading Platform Maintenance Window",
                "body": "David, we need to schedule a maintenance window for the trading platform next Saturday. The SRE team needs to apply security patches to the order management system. Estimated downtime: 2 hours starting at 2 AM EST. Please confirm this works with your team.",
            },
        ],
        "documents": [
            {
                "title": "Internal Network Topology",
                "type": "Technical Diagram",
                "risk_level": "confidential",
                "content": "Meridian Financial operates a segmented network: DMZ (trading APIs), Internal (employee workstations), Restricted (client data). VPN access via Cisco AnyConnect. MFA enforced for all external access. 5 core switches, 22 access switches, 3 firewalls.",
            },
            {
                "title": "Incident Response Plan",
                "type": "Procedure",
                "risk_level": "internal",
                "content": "Tier 1: Automated alerts to SOC team. Tier 2: Incident analysis by security team within 15 minutes. Tier 3: Executive notification if client data involved. Escalation contacts: CISO (primary), CIO (secondary), CEO (tertiary).",
            },
        ],
        "infrastructure": {
            "domain": "meridian-fin.internal",
            "servers": [
                {
                    "hostname": "TRADE-API-01",
                    "ip": "10.20.1.10",
                    "role": "Trading API",
                    "os": "RHEL 9",
                    "services": ["f5-nginx/1.26", "java/17"],
                },
                {
                    "hostname": "TRADE-API-02",
                    "ip": "10.20.1.11",
                    "role": "Trading API",
                    "os": "RHEL 9",
                    "services": ["f5-nginx/1.26", "java/17"],
                },
                {
                    "hostname": "OMS-01",
                    "ip": "10.20.2.10",
                    "role": "Order Management",
                    "os": "RHEL 9",
                    "services": ["ibm-mq/9.3", "java/17"],
                },
                {
                    "hostname": "DB-CORE-01",
                    "ip": "10.20.3.10",
                    "role": "Core Database",
                    "os": "RHEL 9",
                    "services": ["oracle/19c"],
                },
                {
                    "hostname": "DC-01",
                    "ip": "10.20.0.10",
                    "role": "Domain Controller",
                    "os": "Windows Server 2022",
                    "services": ["AD", "DNS", "DHCP"],
                },
                {
                    "hostname": "SOC-01",
                    "ip": "10.20.0.50",
                    "role": "SIEM Collector",
                    "os": "Ubuntu 22.04",
                    "services": ["splunk/9.1"],
                },
                {
                    "hostname": "FILE-01",
                    "ip": "10.20.4.10",
                    "role": "File Server",
                    "os": "Windows Server 2022",
                    "services": ["SMB", "DFS"],
                },
            ],
            "network_devices": [
                {"hostname": "fw-pa-01", "type": "firewall", "vendor": "Palo Alto", "mgmt_ip": "10.20.255.1"},
                {"hostname": "fw-pa-02", "type": "firewall", "vendor": "Palo Alto", "mgmt_ip": "10.20.255.2"},
                {"hostname": "sw-core-01", "type": "switch", "vendor": "Cisco Nexus", "mgmt_ip": "10.20.255.10"},
                {"hostname": "sw-core-02", "type": "switch", "vendor": "Cisco Nexus", "mgmt_ip": "10.20.255.11"},
                {"hostname": "lb-f5-01", "type": "load_balancer", "vendor": "F5 BIG-IP", "mgmt_ip": "10.20.255.20"},
            ],
            "subnets": [
                {"name": "Management", "cidr": "10.20.0.0/24", "vlan_id": 100},
                {"name": "DMZ-Trading", "cidr": "10.20.1.0/24", "vlan_id": 200},
                {"name": "App-Tier", "cidr": "10.20.2.0/24", "vlan_id": 300},
                {"name": "DB-Tier", "cidr": "10.20.3.0/24", "vlan_id": 400},
                {"name": "Internal-Services", "cidr": "10.20.4.0/24", "vlan_id": 500},
            ],
            "cloud_infra": {
                "provider": "Azure",
                "account_id": "987654321098",
                "resources": ["Azure SQL: mf-trading-db", "AKS: trading-k8s-prod", "Blob: trade-logs"],
            },
        },
        "network_depth": {
            "dns_records": [
                {"name": "meridian-fin.internal", "type": "A", "value": "10.20.1.10", "ttl": 300},
                {"name": "trade-api.meridian-fin.internal", "type": "A", "value": "10.20.1.10", "ttl": 300},
                {"name": "trade-api-b.meridian-fin.internal", "type": "A", "value": "10.20.1.11", "ttl": 300},
                {"name": "oms.meridian-fin.internal", "type": "A", "value": "10.20.2.10", "ttl": 3600},
                {
                    "name": "db-core.meridian-fin.internal",
                    "type": "CNAME",
                    "value": "db-core-01.meridian-fin.internal",
                    "ttl": 3600,
                },
                {"name": "soc.meridian-fin.internal", "type": "A", "value": "10.20.0.50", "ttl": 3600},
                {"name": "mail.meridian-fin.com", "type": "MX", "value": "10 mail-proxy.meridian-fin.com", "ttl": 3600},
            ],
            "load_balancers": [
                {
                    "hostname": "lb-f5-01",
                    "type": "f5_bigip",
                    "ip": "10.20.1.5",
                    "upstream_pool": ["TRADE-API-01:443", "TRADE-API-02:443"],
                    "listeners": [
                        {"port": 443, "protocol": "HTTPS", "backend": "trade-api-pool"},
                        {"port": 8443, "protocol": "TCP", "backend": "fix-gateway-pool"},
                    ],
                },
            ],
            "ssl_certs": [
                {
                    "hostname": "trade.meridian-fin.com",
                    "issuer": "DigiCert",
                    "subject": "CN=trade.meridian-fin.com",
                    "valid_from": "2024-03-01",
                    "valid_to": "2025-03-01",
                    "san": ["trade.meridian-fin.com", "api.meridian-fin.com"],
                    "self_signed": False,
                    "weak_cipher": False,
                },
                {
                    "hostname": "lb-f5-01",
                    "issuer": "Internal CA",
                    "subject": "CN=lb-f5-01.meridian-fin.internal",
                    "valid_from": "2024-06-01",
                    "valid_to": "2025-06-01",
                    "san": ["lb-f5-01.meridian-fin.internal"],
                    "self_signed": False,
                    "weak_cipher": False,
                },
            ],
            "active_alerts": [
                {
                    "source": "Splunk",
                    "type": "Correlation Alert",
                    "message": "Unusual login time for user Amanda Foster — successful authentication from IP 10.20.0.100 at 03:14 AM (outside business hours). No prior activity from this workstation.",
                    "severity": "medium",
                    "affected_host": "DC-01 (10.20.0.10)",
                    "timestamp": "1 hour ago",
                },
                {
                    "source": "Palo Alto",
                    "type": "Firewall Block",
                    "message": "Port scan detected from internal IP 10.20.4.50 targeting DB-Tier subnet — 14 ports scanned in 3 seconds. Possible lateral movement.",
                    "severity": "low",
                    "affected_host": "DB-Tier (10.20.3.0/24)",
                    "timestamp": "4 hours ago",
                },
            ],
        },
        "security_config": {
            "firewall_rules": [
                {
                    "source": "0.0.0.0/0",
                    "destination": "lb-f5-01",
                    "port": "443",
                    "protocol": "TCP",
                    "action": "ALLOW",
                    "purpose": "Public trading HTTPS",
                },
                {
                    "source": "lb-f5-01",
                    "destination": "TRADE-API-01, TRADE-API-02",
                    "port": "8443",
                    "protocol": "TCP",
                    "action": "ALLOW",
                    "purpose": "FIX protocol traffic",
                },
                {
                    "source": "TRADE-API-01, TRADE-API-02",
                    "destination": "OMS-01",
                    "port": "1414",
                    "protocol": "TCP",
                    "action": "ALLOW",
                    "purpose": "IBM MQ order submission",
                },
                {
                    "source": "OMS-01",
                    "destination": "DB-CORE-01",
                    "port": "1521",
                    "protocol": "TCP",
                    "action": "ALLOW",
                    "purpose": "Oracle DB queries",
                },
                {
                    "source": "10.20.0.0/24",
                    "destination": "Any",
                    "port": "3389",
                    "protocol": "TCP",
                    "action": "ALLOW",
                    "purpose": "RDP from management subnet",
                },
                {
                    "source": "0.0.0.0/0",
                    "destination": "Any",
                    "port": "3389",
                    "protocol": "TCP",
                    "action": "DENY",
                    "purpose": "Block external RDP",
                },
            ],
            "edr_status": "CrowdStrike Falcon",
            "edr_coverage": "All production servers",
            "patch_gaps": [
                {"hostname": "TRADE-API-01", "missing_patch": "CVE-2024-21626", "severity": "High"},
            ],
            "service_accounts": [
                {"username": "svc_oms", "privilege_level": "Local Admin", "used_by": "Order Management System"},
                {"username": "svc_splunk_fwd", "privilege_level": "Standard", "used_by": "Splunk Universal Forwarder"},
            ],
            "vpn_config": {"provider": "Cisco AnyConnect", "endpoint": "vpn.meridian-fin.com", "auth_method": "MFA"},
        },
        "attack_artifacts": [
            {
                "type": "config_file",
                "name": "oms_application.properties",
                "location": "/opt/oms/config/oms_application.properties",
                "content_excerpt": "mq.queue.manager=OMS_QMANAGER\nmq.channel=SVCOMS.CHL\nmq.password=Str0ng!Pass2024",
                "severity": "medium",
                "description": "IBM MQ password in plaintext config — allows message queue access for order injection",
            },
            {
                "type": "api_key",
                "name": "fix_gateway_key.pem",
                "location": "/etc/fix/gateway/fix_gateway_key.pem",
                "content_excerpt": "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEAw5yGl0iMj4z7Fv8K0kM3R6L9...",
                "severity": "high",
                "description": "FIX gateway private key — could decrypt and replay trading messages",
            },
        ],
        "devops_pipeline": {
            "ci_cd_pipelines": [
                {
                    "name": "trading-platform-pipeline",
                    "platform": "Jenkins",
                    "url": "https://jenkins.meridian-fin.internal/job/trading-platform",
                    "misconfigurations": ["Build artifacts stored without retention limit — 2TB accumulated"],
                    "jobs": [
                        {"name": "compile", "stage": "Build", "script_summary": "mvn clean compile -Pproduction"},
                        {
                            "name": "unit-test",
                            "stage": "Quality",
                            "script_summary": "mvn test -Dexclude=integration/**",
                        },
                        {
                            "name": "integration-test",
                            "stage": "Quality",
                            "script_summary": "mvn verify -Pintegration -Dtestcontainers.reuse=true",
                        },
                        {
                            "name": "vulnerability-scan",
                            "stage": "Security",
                            "script_summary": "trivy image --severity CRITICAL --fail-on-discovery $IMAGE_TAG",
                        },
                        {
                            "name": "deploy-canary",
                            "stage": "Deploy",
                            "script_summary": "kubectl set image deployment/trade-api-canary trade-api=$IMAGE_TAG -n trading",
                        },
                    ],
                },
            ],
            "source_leaks": [
                {
                    "platform": "GitLab Gist",
                    "url": "https://gist.gitlab.com/mtorres/abc123def456",
                    "repo_name": "network-diagram-snippet",
                    "leaked_content": "# Internal VLAN layout\n# Management: 10.20.0.0/24 (VLAN 100)\n# DMZ-Trading: 10.20.1.0/24 (VLAN 200)",
                    "exposure_date": "2024-05-20",
                    "severity": "low",
                },
            ],
            "container_registries": [
                {
                    "registry_url": "harbor.meridian-fin.internal",
                    "provider": "Harbor",
                    "repositories": [
                        {
                            "name": "trade-api",
                            "tags": ["latest", "v4.2.1", "v4.2.0"],
                            "vulnerability_count": 2,
                            "critical_vulns": 0,
                        },
                        {
                            "name": "order-service",
                            "tags": ["latest", "v3.1.5"],
                            "vulnerability_count": 1,
                            "critical_vulns": 0,
                        },
                    ],
                },
            ],
            "terraform_state": {
                "backend_type": "AzureRM",
                "state_file_url": "https://mf-tfstate.sa.core.windows.net/prod/terraform.tfstate",
                "resources": [
                    "azurerm_kubernetes_cluster.trading-prod",
                    "azurerm_mssql_database.trading-db",
                    "azurerm_key_vault.trading-secrets",
                ],
                "exposed_secrets": [],
            },
        },
    },
    {
        "name": "Atlas Healthcare Partners",
        "industry": "Healthcare",
        "size": "large",
        "location": "Boston, MA",
        "description": "A network of 12 hospitals and 45 outpatient clinics providing integrated healthcare services with a focus on telemedicine and AI-assisted diagnostics.",
        "founded_year": 2010,
        "revenue": "$1.2B",
        "employees": [
            {"name": "Dr. Patricia Okonkwo", "title": "Chief Medical Officer", "department": "Medical"},
            {"name": "Thomas Gray", "title": "IT Director", "department": "IT"},
            {"name": "Rachel Simmons", "title": "HIPAA Compliance Lead", "department": "Compliance"},
            {"name": "Kevin Huang", "title": "Systems Administrator", "department": "Infrastructure"},
        ],
        "emails": [
            {
                "from": "thomas.gray@atlashp.com",
                "to": "it-team@atlashp.com",
                "subject": "EHR System Upgrade - Urgent",
                "body": "Team, the Epic EHR upgrade has been pushed forward to this weekend due to a critical security finding. Vendor has released a patch for CVE-2026-1234 affecting patient record encryption. All hands on deck Saturday 8 AM - 8 PM. I need confirmation by EOD.",
            },
        ],
        "documents": [
            {
                "title": "Patient Data Access Audit",
                "type": "Audit Report",
                "risk_level": "confidential",
                "content": "Audit period: Jan-Jun 2024. Total accesses: 847,293. Unauthorized access attempts: 1,247 (0.15%). Average response time: 4.2 minutes. Recommendations: Implement zero-trust architecture for EHR access.",
            },
        ],
        "infrastructure": {
            "domain": "atlashp.internal",
            "servers": [
                {
                    "hostname": "EHR-WEB-01",
                    "ip": "10.30.1.10",
                    "role": "EHR Web Frontend",
                    "os": "Windows Server 2019",
                    "services": ["iis/10", "epic-web/2024"],
                },
                {
                    "hostname": "EHR-APP-01",
                    "ip": "10.30.2.10",
                    "role": "EHR Application",
                    "os": "Windows Server 2019",
                    "services": ["epic-app/2024", "sql-server-native"],
                },
                {
                    "hostname": "PACS-01",
                    "ip": "10.30.2.20",
                    "role": "PACS Imaging",
                    "os": "Windows Server 2019",
                    "services": ["dicom/3.0", "pacs-server/2023"],
                },
                {
                    "hostname": "DB-EHR-01",
                    "ip": "10.30.3.10",
                    "role": "EHR Database",
                    "os": "Windows Server 2022",
                    "services": ["mssql/2022"],
                },
                {
                    "hostname": "DC-01",
                    "ip": "10.30.0.10",
                    "role": "Domain Controller",
                    "os": "Windows Server 2012 R2",
                    "services": ["AD", "DNS", "DHCP"],
                },
                {
                    "hostname": "CITRIX-01",
                    "ip": "10.30.4.10",
                    "role": "Citrix Gateway",
                    "os": "Windows Server 2019",
                    "services": ["citrix-gateway/13"],
                },
                {
                    "hostname": "BACKUP-01",
                    "ip": "10.30.4.20",
                    "role": "Backup Server",
                    "os": "Windows Server 2019",
                    "services": ["veeam-bnr/12"],
                },
            ],
            "network_devices": [
                {"hostname": "fw-main-01", "type": "firewall", "vendor": "SonicWall", "mgmt_ip": "10.30.255.1"},
                {"hostname": "sw-core-01", "type": "switch", "vendor": "Dell PowerConnect", "mgmt_ip": "10.30.255.10"},
                {"hostname": "sw-iot-01", "type": "switch", "vendor": "Dell PowerConnect", "mgmt_ip": "10.30.255.20"},
                {"hostname": "ap-medical-01", "type": "AP", "vendor": "Aruba", "mgmt_ip": "10.30.255.30"},
            ],
            "subnets": [
                {"name": "Management", "cidr": "10.30.0.0/24", "vlan_id": 10},
                {"name": "EHR-Web", "cidr": "10.30.1.0/24", "vlan_id": 20},
                {"name": "EHR-App", "cidr": "10.30.2.0/24", "vlan_id": 30},
                {"name": "EHR-DB", "cidr": "10.30.3.0/24", "vlan_id": 40},
                {"name": "Infrastructure", "cidr": "10.30.4.0/24", "vlan_id": 50},
            ],
            "cloud_infra": {
                "provider": "Azure",
                "account_id": "456789123456",
                "resources": ["Azure SQL: ehr-mirror-db", "Blob: patient-backup-2024"],
            },
        },
        "network_depth": {
            "dns_records": [
                {"name": "atlashp.internal", "type": "A", "value": "10.30.1.10", "ttl": 3600},
                {"name": "ehr.atlashp.internal", "type": "A", "value": "10.30.1.10", "ttl": 300},
                {"name": "pacs.atlashp.internal", "type": "A", "value": "10.30.2.20", "ttl": 3600},
                {"name": "citrix.atlashp.internal", "type": "A", "value": "10.30.4.10", "ttl": 300},
                {
                    "name": "db-ehr.atlashp.internal",
                    "type": "CNAME",
                    "value": "db-ehr-01.atlashp.internal",
                    "ttl": 3600,
                },
                {"name": "mail.atlashp.com", "type": "MX", "value": "10 smtp.atlashp.com", "ttl": 3600},
                {"name": "legacy-ehr.atlashp.internal", "type": "A", "value": "192.168.50.10", "ttl": 86400},
            ],
            "load_balancers": [
                {
                    "hostname": "lb-ehr-01",
                    "type": "kemp",
                    "ip": "10.30.1.5",
                    "upstream_pool": ["EHR-WEB-01:443"],
                    "listeners": [{"port": 443, "protocol": "HTTPS", "backend": "ehr-web-pool"}],
                },
            ],
            "ssl_certs": [
                {
                    "hostname": "ehr.atlashp.com",
                    "issuer": "Let's Encrypt",
                    "subject": "CN=ehr.atlashp.com",
                    "valid_from": "2024-01-01",
                    "valid_to": "2025-01-01",
                    "san": ["ehr.atlashp.com"],
                    "self_signed": False,
                    "weak_cipher": False,
                },
                {
                    "hostname": "citrix.atlashp.internal",
                    "issuer": "Self-Signed",
                    "subject": "CN=citrix.atlashp.internal",
                    "valid_from": "2022-01-01",
                    "valid_to": "2023-01-01",
                    "san": ["citrix.atlashp.internal"],
                    "self_signed": True,
                    "weak_cipher": True,
                },
                {
                    "hostname": "legacy-ehr.atlashp.internal",
                    "issuer": "Self-Signed",
                    "subject": "CN=legacy-ehr.atlashp.internal",
                    "valid_from": "2020-06-01",
                    "valid_to": "2021-06-01",
                    "san": ["legacy-ehr.atlashp.internal"],
                    "self_signed": True,
                    "weak_cipher": True,
                },
            ],
            "active_alerts": [
                {
                    "source": "Windows Event ID 4625",
                    "type": "Event Log",
                    "message": "Multiple failed logon attempts for Administrator account from IP 10.30.4.50 — 53 attempts in 5 minutes. Possible brute force attack on DC-01.",
                    "severity": "critical",
                    "affected_host": "DC-01 (10.30.0.10)",
                    "timestamp": "10 min ago",
                },
                {
                    "source": "SonicWall",
                    "type": "Firewall Block",
                    "message": "Outbound traffic from PACS-01 to known ransomware C2 domain (evilcorp.xyz:443). TLS handshake detected. Process: unknown.",
                    "severity": "critical",
                    "affected_host": "PACS-01 (10.30.2.20)",
                    "timestamp": "25 min ago",
                },
                {
                    "source": "Windows Defender",
                    "type": "EDR Detection",
                    "message": "Potential ransomware behavior detected on CITRIX-01. Files being encrypted with .atlas_crypt extension in C:\\Citrix\\Storage.",
                    "severity": "critical",
                    "affected_host": "CITRIX-01 (10.30.4.10)",
                    "timestamp": "35 min ago",
                },
                {
                    "source": "Veeam",
                    "type": "Backup Alert",
                    "message": "Backup job 'EHR-Full-Daily' has been failing for 3 consecutive days. Last successful backup: 2024-06-09. Check storage repository connectivity.",
                    "severity": "high",
                    "affected_host": "BACKUP-01 (10.30.4.20)",
                    "timestamp": "2 hours ago",
                },
            ],
        },
        "security_config": {
            "firewall_rules": [
                {
                    "source": "0.0.0.0/0",
                    "destination": "CITRIX-01",
                    "port": "443",
                    "protocol": "TCP",
                    "action": "ALLOW",
                    "purpose": "Citrix remote access",
                },
                {
                    "source": "CITRIX-01",
                    "destination": "EHR-APP-01",
                    "port": "443",
                    "protocol": "TCP",
                    "action": "ALLOW",
                    "purpose": "Citrix to EHR app",
                },
                {
                    "source": "EHR-WEB-01",
                    "destination": "EHR-APP-01",
                    "port": "8080",
                    "protocol": "TCP",
                    "action": "ALLOW",
                    "purpose": "Web to app tier",
                },
                {
                    "source": "EHR-APP-01",
                    "destination": "DB-EHR-01",
                    "port": "1433",
                    "protocol": "TCP",
                    "action": "ALLOW",
                    "purpose": "MSSQL queries",
                },
                {
                    "source": "EHR-WEB-01",
                    "destination": "DB-EHR-01",
                    "port": "1433",
                    "protocol": "TCP",
                    "action": "ALLOW",
                    "purpose": "Direct DB access from web",
                },
                {
                    "source": "0.0.0.0/0",
                    "destination": "Any",
                    "port": "3389",
                    "protocol": "TCP",
                    "action": "DENY",
                    "purpose": "Block external RDP",
                },
            ],
            "edr_status": "Windows Defender",
            "edr_coverage": "Only critical servers",
            "patch_gaps": [
                {"hostname": "DC-01", "missing_patch": "CVE-2024-26234", "severity": "Critical"},
                {"hostname": "EHR-WEB-01", "missing_patch": "CVE-2024-28995", "severity": "Critical"},
                {"hostname": "PACS-01", "missing_patch": "CVE-2024-38077", "severity": "High"},
            ],
            "service_accounts": [
                {
                    "username": "svc_ehr_sync",
                    "privilege_level": "Domain Admin",
                    "used_by": "EHR Synchronization Service",
                },
                {"username": "svc_backup", "privilege_level": "Domain Admin", "used_by": "Veeam Backup Service"},
                {"username": "svc_pacs", "privilege_level": "Local Admin", "used_by": "PACS DICOM Service"},
            ],
            "vpn_config": {"provider": "OpenVPN", "endpoint": "vpn.atlashp.com", "auth_method": "Password only"},
        },
        "attack_artifacts": [
            {
                "type": "config_file",
                "name": "epic_db_connection.ini",
                "location": "C:\\Program Files\\Epic\\Config\\epic_db_connection.ini",
                "content_excerpt": "[Database]\nserver=DB-EHR-01\ndatabase=EpicProduction\nauthentication=SQL Server\nusername=sa\npassword=Ep!cD@t@b@$e2024",
                "severity": "critical",
                "description": "SQL Server SA credentials in plaintext — grants full access to the Epic EHR production database containing all patient records",
            },
            {
                "type": "backup_file",
                "name": "EHR_Full_Dump_20240601.bak",
                "location": "\\\\BACKUP-01\\EHR_Backups\\EHR_Full_Dump_20240601.bak",
                "content_excerpt": "BAK file header: EpicProduction_Full_20240601.bak (1.2 TB). Contains: PatientDemographics(12M rows), MedicalHistory, BillingInfo, InsuranceEligibility",
                "severity": "critical",
                "description": "Full database backup containing 12M patient records — prime target for exfiltration",
            },
            {
                "type": "password_manager",
                "name": "IT_Admin_Credentials.kdbx",
                "location": "\\\\FILE-01\\Shared\\IT\\IT_Admin_Credentials.kdbx",
                "content_excerpt": "KeePass database. Entries include: DC-01 local admin, EHR service account, AWS console root, SharePoint global admin",
                "severity": "critical",
                "description": "KeePass database shared on network share with default master password 'admin123' — domain-level compromise",
            },
        ],
        "devops_pipeline": {
            "ci_cd_pipelines": [
                {
                    "name": "ehr-deploy-pipeline",
                    "platform": "Jenkins",
                    "url": "https://jenkins.atlashp.internal/job/ehr-deploy",
                    "misconfigurations": [
                        "Hardcoded domain admin credentials in Jenkins config.xml",
                        "No code review or approval gates",
                        "Disabled SSL verification on all webhook calls",
                    ],
                    "jobs": [
                        {
                            "name": "build",
                            "stage": "Build",
                            "script_summary": "msbuild EpicSolution.sln /p:Configuration=Release",
                        },
                        {
                            "name": "deploy-ehr",
                            "stage": "Deploy",
                            "script_summary": "powershell -ExecutionPolicy Bypass -File deploy_ehr.ps1 -Server EHR-WEB-01 -Credential $ADMIN_CRED",
                        },
                        {
                            "name": "db-migrate",
                            "stage": "Database",
                            "script_summary": "sqlcmd -S DB-EHR-01 -U sa -P $DB_PASS -i migration.sql",
                        },
                    ],
                },
            ],
            "source_leaks": [
                {
                    "platform": "Pastebin",
                    "url": "https://pastebin.com/raw/AtLasHcLeaK",
                    "repo_name": "EHR-DB-Config-Backup",
                    "leaked_content": "Server: DB-EHR-01\nDatabase: EpicProduction\nUser: sa\nPass: Ep!cD@t@b@$e2024\nConnString: DRIVER={ODBC Driver 17 for SQL Server};SERVER=DB-EHR-01;DATABASE=EpicProduction;UID=sa;PWD=Ep!cD@t@b@$e2024",
                    "exposure_date": "2024-04-01",
                    "severity": "critical",
                },
                {
                    "platform": "GitHub",
                    "url": "https://github.com/akh-devops/ehr-scripts",
                    "repo_name": "ehr-scripts",
                    "leaked_content": "SMB share credentials for backup restore:\nnet use Z: \\\\BACKUP-01\\EHR_Backups /user:ATHC\\svc_backup Back!p@ss123",
                    "exposure_date": "2024-02-28",
                    "severity": "high",
                },
            ],
            "container_registries": [
                {
                    "registry_url": "docker.io/atlashc",
                    "provider": "Docker Hub",
                    "repositories": [
                        {
                            "name": "ehr-web-frontend",
                            "tags": ["latest", "v2024.3", "v2024.2"],
                            "vulnerability_count": 47,
                            "critical_vulns": 12,
                        },
                        {
                            "name": "pacs-viewer",
                            "tags": ["latest", "v3.0.1"],
                            "vulnerability_count": 31,
                            "critical_vulns": 8,
                        },
                        {
                            "name": "citrix-gateway-wrapper",
                            "tags": ["latest"],
                            "vulnerability_count": 23,
                            "critical_vulns": 5,
                        },
                    ],
                },
            ],
            "terraform_state": {
                "backend_type": "S3",
                "state_file_url": "s3://atlashp-tf-backup-2024/terraform.tfstate",
                "resources": [
                    "azurerm_sql_database.ehr-mirror",
                    "azurerm_storage_account.patient_backup",
                    "azurerm_key_vault.ehr-keys",
                    "azurerm_virtual_network.ehr-vnet",
                ],
                "exposed_secrets": [
                    "azurerm_key_vault.ehr-keys - access_policy[0].object_id",
                    "AZURE_CLIENT_SECRET",
                    "SQL_ADMIN_PASSWORD",
                ],
            },
        },
    },
]


async def seed_default_tasks():
    from sqlalchemy import select

    from backend.database import get_session
    from backend.models.user import User

    async for db in get_session():
        result = await db.execute(select(User).limit(1))
        if result.scalar_one_or_none() is not None:
            return
    for company in SEED_COMPANIES:
        task_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"shadowhive-seed-{company['industry']}-{company['size']}"))
        if task_id in task_manager._tasks:
            continue
        task = Task(
            "company_generation",
            {
                "industry": company["industry"],
                "size": company["size"],
            },
        )
        task.id = task_id
        task.status = TaskStatus.COMPLETED
        task.progress = 100.0
        task.message = "Generation complete"
        task.result = company
        task.started_at = _naive_utcnow()
        task.completed_at = _naive_utcnow()
        task_manager._tasks[task_id] = task
        await task_manager._persist(task)
