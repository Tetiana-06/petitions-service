from typing import Optional

from pydantic import BaseModel


class UserCreate(BaseModel):
    username: str
    password: str
    role: Optional[str] = "user"


class UserResponse(BaseModel):
    id: int
    username: str
    role: str

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


class PetitionCreate(BaseModel):
    title: str
    description: str
    target_votes: int = 1000


class PetitionUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None


class PetitionResponse(BaseModel):
    id: int
    title: str
    description: str
    target_votes: int
    author_id: int

    class Config:
        from_attributes = True


class VoteCreate(BaseModel):
    voter_signature_hash: str
