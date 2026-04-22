"""
Logs router — receive frontend logs and serve log data.
"""
import os
from datetime import datetime, timezone
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings
from logger import get_logger, get_frontend_logger, log_action

logger = get_logger("logs_router")
frontend_logger = get_frontend_logger()
router = APIRouter(prefix="/logs", tags=["Logs"])


class FrontendLogEntry(BaseModel):
    level: str = "info"
    component: str = "frontend"
    action: str = ""
    details: str = ""
    timestamp: Optional[str] = None


@router.post("")
async def receive_frontend_log(entry: FrontendLogEntry):
    """Receive and store a log entry from the frontend."""
    ts = entry.timestamp or datetime.now(timezone.utc).isoformat()
    log_action(frontend_logger, entry.level, entry.component, entry.action, entry.details)
    return {"success": True}


@router.get("")
async def get_logs(limit: int = 100, level: str = "INFO", source: str = "app"):
    """Retrieve recent log entries."""
    log_file = os.path.join(settings.LOG_DIR, f"{source}.log")

    if not os.path.exists(log_file):
        return {"success": True, "logs": [], "message": f"No {source}.log file found"}

    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # Filter by level
        level_priority = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
        min_priority = level_priority.get(level.upper(), 0)

        filtered = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            for lev, pri in level_priority.items():
                if f"| {lev}" in line and pri >= min_priority:
                    filtered.append(line)
                    break

        # Return last N entries
        recent = filtered[-limit:]

        log_action(logger, "debug", "logs_router", "LOGS_RETRIEVED",
                   f"source={source} | level={level} | total={len(filtered)} | returned={len(recent)}")

        return {"success": True, "logs": recent, "total": len(filtered)}

    except Exception as e:
        return {"success": False, "error": str(e)}
