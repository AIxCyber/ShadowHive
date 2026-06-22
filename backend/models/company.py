import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Column, DateTime, Float, String, Text, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase


def _naive_utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid(as_uuid=True), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    industry = Column(String(255), nullable=False)
    size = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    location_city = Column(String(255), nullable=True)
    location_country = Column(String(255), nullable=True)
    founded_year = Column(String(4), nullable=True)
    org_chart = Column(JSON, nullable=True)
    extra_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: _naive_utcnow())
    updated_at = Column(DateTime, default=lambda: _naive_utcnow(), onupdate=lambda: _naive_utcnow())
    status = Column(String(20), default="active")


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(Uuid(as_uuid=True), nullable=False)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255), nullable=False)
    title = Column(String(255), nullable=False)
    department = Column(String(255), nullable=False)
    manager_id = Column(Uuid(as_uuid=True), nullable=True)
    bio = Column(Text, nullable=True)
    skills = Column(JSON, nullable=True)
    personality = Column(JSON, nullable=True)
    extra_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: _naive_utcnow())
    updated_at = Column(DateTime, default=lambda: _naive_utcnow(), onupdate=lambda: _naive_utcnow())
    status = Column(String(20), default="active")


class Email(Base):
    __tablename__ = "emails"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(Uuid(as_uuid=True), nullable=False)
    thread_id = Column(Uuid(as_uuid=True), nullable=True)
    sender_id = Column(Uuid(as_uuid=True), nullable=False)
    recipient_ids = Column(JSON, nullable=False)
    subject = Column(String(512), nullable=False)
    body = Column(Text, nullable=False)
    sent_at = Column(DateTime, nullable=False)
    is_internal = Column(SAEnum("true", "false", name="bool_enum"), default=True)
    extra_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: _naive_utcnow())


class Document(Base):
    __tablename__ = "documents"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(Uuid(as_uuid=True), nullable=False)
    author_id = Column(Uuid(as_uuid=True), nullable=True)
    title = Column(String(512), nullable=False)
    doc_type = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    file_path = Column(String(1024), nullable=True)
    extra_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: _naive_utcnow())
    updated_at = Column(DateTime, default=lambda: _naive_utcnow(), onupdate=lambda: _naive_utcnow())


class CompanyProfile(Base):
    __tablename__ = "company_profiles"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid(as_uuid=True), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    industry = Column(String(100), nullable=True)
    size = Column(String(50), nullable=True)
    company_name = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    location = Column(String(255), nullable=True)
    technologies = Column(JSON, nullable=True)
    security_posture = Column(String(50), default="default")
    created_at = Column(DateTime, default=lambda: _naive_utcnow())
    updated_at = Column(DateTime, default=lambda: _naive_utcnow(), onupdate=lambda: _naive_utcnow())


class AttackerEvent(Base):
    __tablename__ = "attacker_events"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid(as_uuid=True), nullable=True, index=True)
    company_id = Column(Uuid(as_uuid=True), nullable=False)
    source_ip = Column(String(45), nullable=False)
    event_type = Column(String(100), nullable=False)
    command = Column(Text, nullable=True)
    session_id = Column(String(255), nullable=True)
    mitre_technique_id = Column(String(50), nullable=True)
    mitre_tactic = Column(String(100), nullable=True)
    confidence_score = Column(String(10), nullable=True)
    severity = Column(String(20), default="medium")
    raw_data = Column(JSON, nullable=True)
    detected_at = Column(DateTime, default=lambda: _naive_utcnow())
    created_at = Column(DateTime, default=lambda: _naive_utcnow())


# ── Infrastructure models (populated when enrich=True) ─────────────────────


class Server(Base):
    __tablename__ = "servers"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    hostname = Column(String(255), nullable=False)
    ip = Column(String(45), nullable=False)
    role = Column(String(100), nullable=True)
    os = Column(String(100), nullable=True)
    services = Column(JSON, nullable=True)
    extra_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: _naive_utcnow())


class NetworkDevice(Base):
    __tablename__ = "network_devices"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    hostname = Column(String(255), nullable=False)
    device_type = Column(String(50), nullable=True)
    vendor = Column(String(100), nullable=True)
    mgmt_ip = Column(String(45), nullable=True)
    extra_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: _naive_utcnow())


class Subnet(Base):
    __tablename__ = "subnets"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    cidr = Column(String(45), nullable=False)
    vlan_id = Column(String(10), nullable=True)
    extra_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: _naive_utcnow())


class CloudInfra(Base):
    __tablename__ = "cloud_infras"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    provider = Column(String(100), nullable=False)
    account_id = Column(String(100), nullable=True)
    resources = Column(JSON, nullable=True)
    extra_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: _naive_utcnow())


class DnsRecord(Base):
    __tablename__ = "dns_records"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    name = Column(String(512), nullable=False)
    record_type = Column(String(10), nullable=False)
    value = Column(String(512), nullable=False)
    ttl = Column(String(10), nullable=True)
    extra_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: _naive_utcnow())


class LoadBalancer(Base):
    __tablename__ = "load_balancers"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    hostname = Column(String(255), nullable=False)
    lb_type = Column(String(50), nullable=True)
    ip = Column(String(45), nullable=True)
    upstream_pool = Column(JSON, nullable=True)
    extra_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: _naive_utcnow())


class SslCert(Base):
    __tablename__ = "ssl_certs"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    hostname = Column(String(255), nullable=False)
    issuer = Column(String(255), nullable=True)
    subject = Column(String(512), nullable=True)
    valid_from = Column(String(20), nullable=True)
    valid_to = Column(String(20), nullable=True)
    san = Column(JSON, nullable=True)
    self_signed = Column(String(5), default="false")
    weak_cipher = Column(String(5), default="false")
    extra_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: _naive_utcnow())


class ActiveAlert(Base):
    __tablename__ = "active_alerts"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    source = Column(String(100), nullable=True)
    alert_type = Column(String(100), nullable=True)
    message = Column(Text, nullable=True)
    severity = Column(String(20), nullable=True)
    affected_host = Column(String(255), nullable=True)
    extra_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: _naive_utcnow())


class CiCdPipeline(Base):
    __tablename__ = "ci_cd_pipelines"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    platform = Column(String(100), nullable=True)
    url = Column(String(1024), nullable=True)
    misconfigurations = Column(JSON, nullable=True)
    extra_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: _naive_utcnow())


class SourceLeak(Base):
    __tablename__ = "source_leaks"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    platform = Column(String(100), nullable=True)
    url = Column(String(1024), nullable=True)
    repo_name = Column(String(255), nullable=True)
    leaked_content = Column(Text, nullable=True)
    exposure_date = Column(String(20), nullable=True)
    severity = Column(String(20), nullable=True)
    extra_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: _naive_utcnow())


class ContainerRegistry(Base):
    __tablename__ = "container_registries"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    registry_url = Column(String(1024), nullable=True)
    provider = Column(String(100), nullable=True)
    extra_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: _naive_utcnow())


class TerraformState(Base):
    __tablename__ = "terraform_states"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    backend_type = Column(String(50), nullable=True)
    state_file_url = Column(String(1024), nullable=True)
    resources = Column(JSON, nullable=True)
    exposed_secrets = Column(JSON, nullable=True)
    extra_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: _naive_utcnow())


class FirewallRule(Base):
    __tablename__ = "firewall_rules"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    source = Column(String(45), nullable=True)
    destination = Column(String(45), nullable=True)
    port = Column(String(20), nullable=True)
    protocol = Column(String(10), nullable=True)
    action = Column(String(10), nullable=True)
    purpose = Column(Text, nullable=True)
    extra_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: _naive_utcnow())


class PatchGap(Base):
    __tablename__ = "patch_gaps"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    hostname = Column(String(255), nullable=True)
    missing_patch = Column(String(255), nullable=True)
    severity = Column(String(20), nullable=True)
    extra_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: _naive_utcnow())


class ServiceAccount(Base):
    __tablename__ = "service_accounts"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    username = Column(String(255), nullable=False)
    privilege_level = Column(String(50), nullable=True)
    used_by = Column(String(255), nullable=True)
    extra_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: _naive_utcnow())


class VpnConfig(Base):
    __tablename__ = "vpn_configs"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    provider = Column(String(100), nullable=True)
    endpoint = Column(String(255), nullable=True)
    auth_method = Column(String(50), nullable=True)
    extra_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: _naive_utcnow())


class AttackArtifact(Base):
    __tablename__ = "attack_artifacts"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    artifact_type = Column(String(100), nullable=False)
    name = Column(String(255), nullable=False)
    location = Column(String(1024), nullable=True)
    content_excerpt = Column(Text, nullable=True)
    severity = Column(String(20), nullable=True)
    description = Column(Text, nullable=True)
    extra_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: _naive_utcnow())


class GenerationTask(Base):
    __tablename__ = "generation_tasks"

    task_id = Column(String, primary_key=True)
    user_id = Column(String, nullable=True, index=True)
    type = Column(String, nullable=False)
    params = Column(JSON, nullable=True)
    status = Column(String, nullable=False, default="pending")
    progress = Column(Float, nullable=False, default=0.0)
    message = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    result = Column(JSON, nullable=True)
    started_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
