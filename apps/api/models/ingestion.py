from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, JSON, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from apps.api.core.database import Base
from apps.api.models.auth import generate_uuid

class Collection(Base):
    __tablename__ = "collections"
    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String)
    description = Column(String, nullable=True)
    tenant_id = Column(String, ForeignKey("tenants.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tenant = relationship("Tenant", back_populates="collections")
    sources = relationship("Source", back_populates="collection")

class Source(Base):
    __tablename__ = "sources"
    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String)
    type = Column(String) # code, doc
    config = Column(JSON) # repo_url, file_path, etc.
    collection_id = Column(String, ForeignKey("collections.id"))
    tenant_id = Column(String, ForeignKey("tenants.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    collection = relationship("Collection", back_populates="sources")
    tenant = relationship("Tenant", back_populates="sources")
    jobs = relationship("IngestionJob", back_populates="source")

class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    id = Column(String, primary_key=True, default=generate_uuid)
    source_id = Column(String, ForeignKey("sources.id"))
    status = Column(String) # pending, running, completed, failed
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    meta = Column(JSON, nullable=True) # stats

    source = relationship("Source", back_populates="jobs")
    logs = relationship("JobLog", back_populates="job")

class JobLog(Base):
    __tablename__ = "job_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, ForeignKey("ingestion_jobs.id"))
    level = Column(String)
    message = Column(Text)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    job = relationship("IngestionJob", back_populates="logs")
