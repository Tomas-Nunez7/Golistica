from pydantic import BaseModel, Field
from typing import Optional

class LoginIn(BaseModel):
    username: str
    password: str

class UserCreate(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    role_id: int = Field(..., description='1=user,2=operator,3=admin')

class CourtIn(BaseModel):
    name: str
    location: Optional[str] = None
    price: Optional[float] = 0.0

class ReservationIn(BaseModel):
    court_id: int
    start_ts: str
    end_ts: str
    version: Optional[int] = None
