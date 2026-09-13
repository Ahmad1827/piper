from pydantic import BaseModel, HttpUrl, EmailStr
from typing import Optional, Dict, Any

class TenantCreateRequest(BaseModel):
    name: str
    webhook_url: HttpUrl

class TenantResponse(BaseModel):
    id: str
    name: str
    api_key: str
    webhook_secret: str
    webhook_url: str

class SessionCreateRequest(BaseModel):
    amount_cents: int
    currency: str
    item_name: str
    customer_email: Optional[EmailStr] = None
    metadata: Optional[Dict[str, Any]] = {}
    success_url: HttpUrl
    cancel_url: HttpUrl

class SessionResponse(BaseModel):
    session_id: str
    checkout_url: str
    status: str
