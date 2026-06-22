from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CompanyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    industry: str = Field(..., min_length=1, max_length=255)
    size: str = Field(default="medium")
    description: str | None = None
    location_city: str | None = None
    location_country: str | None = None
    founded_year: str | None = None


class CompanyResponse(BaseModel):
    id: UUID
    name: str
    industry: str
    size: str
    description: str | None = None
    location_city: str | None = None
    location_country: str | None = None
    founded_year: str | None = None
    org_chart: dict | None = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EmployeeCreate(BaseModel):
    company_id: UUID
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=255)
    department: str = Field(..., min_length=1, max_length=255)
    bio: str | None = None


class EmployeeResponse(BaseModel):
    id: UUID
    company_id: UUID
    first_name: str
    last_name: str
    email: str
    title: str
    department: str
    manager_id: UUID | None = None
    bio: str | None = None
    skills: list | None = None
    personality: dict | None = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EmailCreate(BaseModel):
    company_id: UUID
    thread_id: UUID | None = None
    sender_id: UUID
    recipient_ids: list[UUID]
    subject: str = Field(..., min_length=1, max_length=512)
    body: str = Field(..., min_length=1)
    sent_at: datetime | None = None
    is_internal: bool = True


class EmailResponse(BaseModel):
    id: UUID
    company_id: UUID
    thread_id: UUID | None = None
    sender_id: UUID
    recipient_ids: list[UUID]
    subject: str
    body: str
    sent_at: datetime
    is_internal: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentCreate(BaseModel):
    company_id: UUID
    author_id: UUID | None = None
    title: str = Field(..., min_length=1, max_length=512)
    doc_type: str = Field(..., min_length=1, max_length=100)
    content: str = Field(..., min_length=1)


class DocumentResponse(BaseModel):
    id: UUID
    company_id: UUID
    author_id: UUID | None = None
    title: str
    doc_type: str
    content: str
    file_path: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
