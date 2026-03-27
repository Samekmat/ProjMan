from datetime import datetime
from typing import List
from uuid import UUID

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    login: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=72)
    repeat_password: str = Field(..., min_length=6, max_length=72)


class UserLogin(BaseModel):
    login: str
    password: str = Field(..., max_length=72)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    description: str | None = Field(None, max_length=500)


class ProjectResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    total_storage_bytes: int
    documents: List["DocumentResponse"] = []


class DocumentCreate(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(..., examples=["application/pdf"])


class DocumentResponse(BaseModel):
    id: UUID
    project_id: UUID
    filename: str
    s3_key: str
    size_bytes: int
    created_at: datetime


class ProjectUpdate(BaseModel):
    name: str | None = Field(None, min_length=3, max_length=100)
    description: str | None = Field(default=None, max_length=500)


class DocumentUpdate(BaseModel):
    filename: str | None = Field(None, min_length=1, max_length=255)
