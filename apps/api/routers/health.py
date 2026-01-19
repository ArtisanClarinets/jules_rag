from fastapi import APIRouter
from apps.api.core.config import settings

router = APIRouter()

@router.get("/health")
def health_check():
    return {"status": "ok", "version": "0.1.0"}
