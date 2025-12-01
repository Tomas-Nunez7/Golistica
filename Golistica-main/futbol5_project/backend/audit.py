import json
import socket
from typing import Optional

from sqlalchemy.orm import Session

from . import models

TCP_ALERT_HOST = "127.0.0.1"
TCP_ALERT_PORT = 9001


def log_action(
    db: Session,
    actor_id: Optional[int],
    actor_username: Optional[str],
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[str] = None,
    success: bool = True,
) -> None:
    entry = models.AuditLog(
        actor_id=actor_id,
        actor_username=actor_username,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        success=success,
    )
    db.add(entry)
    db.commit()


def send_alert(
    db: Session,
    level: str,
    message: str,
    payload: Optional[dict] = None,
) -> None:
    alert = models.Alert(
        level=level,
        message=message,
        payload=json.dumps(payload or {}),
        sent=False,
    )
    db.add(alert)
    db.commit()

    data = json.dumps(
        {
            "level": level,
            "message": message,
            "payload": payload or {},
        },
        ensure_ascii=False,
    ).encode()

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((TCP_ALERT_HOST, TCP_ALERT_PORT))
            s.sendall(data)
        alert.sent = True
        db.commit()
    except OSError:
        # Si no se puede conectar al listener, dejamos sent=False
        db.rollback()
