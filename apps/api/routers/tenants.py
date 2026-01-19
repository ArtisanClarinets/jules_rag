from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from apps.api.core.database import get_db
from apps.api.models.auth import Tenant
from apps.api.schemas.tenant import TenantCreate, Tenant as TenantSchema

router = APIRouter()

@router.post("/", response_model=TenantSchema)
def create_tenant(tenant: TenantCreate, db: Session = Depends(get_db)):
    db_tenant = Tenant(name=tenant.name)
    db.add(db_tenant)
    db.commit()
    db.refresh(db_tenant)
    return db_tenant

@router.get("/", response_model=List[TenantSchema])
def read_tenants(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(Tenant).offset(skip).limit(limit).all()
