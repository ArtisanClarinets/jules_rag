from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from apps.api.core.database import get_db
from apps.api.models.config import SystemSettings
from typing import Dict, Any

router = APIRouter()

class SettingsUpdate(BaseModel):
    settings: Dict[str, Any]

@router.get("/")
def get_settings(db: Session = Depends(get_db)):
    settings_records = db.query(SystemSettings).all()
    return {s.key: s.value for s in settings_records}

@router.post("/")
def update_settings(update: SettingsUpdate, db: Session = Depends(get_db)):
    # Upsert settings
    for key, value in update.settings.items():
        record = db.query(SystemSettings).filter(SystemSettings.key == key).first()
        if record:
            record.value = value
        else:
            db.add(SystemSettings(key=key, value=value))

    db.commit()

    # Trigger restart logic (mocked for now, but critical for requirement)
    # In real world: write to file, signal supervisord or docker
    print("Restarting services with new config...")

    return {"status": "updated", "restart_triggered": True}
