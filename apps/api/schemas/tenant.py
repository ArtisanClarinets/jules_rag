from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class TenantBase(BaseModel):
    name: str

class TenantCreate(TenantBase):
    pass

class TenantUpdate(TenantBase):
    pass

class Tenant(TenantBase):
    id: str
    created_at: datetime

    class Config:
        from_attributes = True
