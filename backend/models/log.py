import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, Uuid

from backend.models.company import Base


class LogEntry(Base):
    __tablename__ = "app_logs"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp = Column(DateTime, nullable=False, index=True)
    level = Column(String(10), nullable=False, index=True)
    logger_name = Column(String(255), nullable=False, index=True)
    module = Column(String(255), nullable=True)
    func_name = Column(String(255), nullable=True)
    line_no = Column(Integer, nullable=True)
    message = Column(Text, nullable=False)
    traceback = Column(Text, nullable=True)
    task_id = Column(String(36), nullable=True, index=True)
    request_id = Column(String(36), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC).replace(tzinfo=None))
