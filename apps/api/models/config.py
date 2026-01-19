from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship
from apps.api.core.database import Base
from apps.api.models.auth import generate_uuid

class Provider(Base):
    __tablename__ = "providers"
    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String)
    type = Column(String) # embedding, rerank, llm
    provider_id = Column(String) # local_cpu, local_gpu, openrouter, custom
    config = Column(JSON) # endpoint, model, api_key_ref, dims
    is_default = Column(Boolean, default=False)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=True) # If null, system default

class SystemSettings(Base):
    __tablename__ = "system_settings"
    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, index=True)
    value = Column(JSON)
