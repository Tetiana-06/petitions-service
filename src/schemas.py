# Схеми валідації запитів/відповідей за допомогою Pydantic v2
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class UserCreate(BaseModel):
    username: str
    password: str
    role: Optional[str] = "user"
    full_name: Optional[str] = None
    email: Optional[str] = None


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
    full_name: Optional[str] = None
    email: Optional[str] = None
    created_at: Optional[datetime] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str
    user: Optional[UserResponse] = None


class PetitionCreate(BaseModel):
    title: str
    description: str
    target_votes: int = 1000


class PetitionUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None


class PetitionStatusUpdate(BaseModel):
    status: str


class PetitionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    target_votes: int
    status: str = "active"
    author_id: int
    author_username: Optional[str] = None
    votes_count: int = 0
    created_at: Optional[datetime] = None


class VoteCreate(BaseModel):
    voter_signature_hash: Optional[str] = None


class AdminStats(BaseModel):
    total_users: int
    total_petitions: int
    total_votes: int
    petitions_by_status: dict[str, int]
