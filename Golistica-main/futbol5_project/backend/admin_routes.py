from datetime import datetime
from typing import List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .db import SessionLocal
from . import models
from .auth import require_admin
from .audit import log_action, send_alert

router = APIRouter(prefix="/api/admin", tags=["admin"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/integrity/check")
def integrity_check(
    db: Session = Depends(get_db),
    current_admin=Depends(require_admin),
) -> Dict[str, Any]:
    """Verifica problemas básicos de integridad en la base de datos."""

    problems: Dict[str, List[dict]] = {
        "reservations_orphan_court": [],
        "reservations_orphan_user": [],
        "reservations_invalid_datetime": [],
    }

    reservations = db.query(models.Reservation).all()
    court_ids = {c.id for c in db.query(models.Court.id).all()}
    user_ids = {u.id for u in db.query(models.User.id).all()}

    for r in reservations:
        if r.court_id not in court_ids:
            problems["reservations_orphan_court"].append({"id": r.id, "court_id": r.court_id})
        if r.user_id is not None and r.user_id not in user_ids:
            problems["reservations_orphan_user"].append({"id": r.id, "user_id": r.user_id})
        try:
            datetime.fromisoformat(r.start_ts)
            datetime.fromisoformat(r.end_ts)
        except ValueError:
            problems["reservations_invalid_datetime"].append({"id": r.id, "start_ts": r.start_ts, "end_ts": r.end_ts})

    log_action(
        db,
        actor_id=current_admin.id,
        actor_username=current_admin.username,
        action="integrity_check",
        resource_type="admin",
        resource_id=None,
        details=f"Problemas detectados: { {k: len(v) for k, v in problems.items()} }",
        success=True,
    )

    return {"problems": problems}


@router.post("/integrity/fix")
def integrity_fix(
    db: Session = Depends(get_db),
    current_admin=Depends(require_admin),
) -> Dict[str, Any]:
    """Marca reservas problemáticas como invalid y recalcula estadísticas de usuarios."""

    # Marcar reservas problemáticas como invalid
    affected_ids: List[int] = []

    reservations = db.query(models.Reservation).all()
    court_ids = {c.id for c in db.query(models.Court.id).all()}
    user_ids = {u.id for u in db.query(models.User.id).all()}

    for r in reservations:
        invalid = False
        if r.court_id not in court_ids:
            invalid = True
        if r.user_id is not None and r.user_id not in user_ids:
            invalid = True
        try:
            datetime.fromisoformat(r.start_ts)
            datetime.fromisoformat(r.end_ts)
        except ValueError:
            invalid = True

        if invalid and r.status != "invalid":
            r.status = "invalid"
            affected_ids.append(r.id)

    # Recalcular StatsUserReservations
    db.query(models.StatsUserReservations).delete()
    db.commit()

    active_counts: Dict[int, int] = {}
    active_reservations = (
        db.query(models.Reservation)
        .filter(models.Reservation.status == "active", models.Reservation.user_id.isnot(None))
        .all()
    )
    for r in active_reservations:
        active_counts[r.user_id] = active_counts.get(r.user_id, 0) + 1

    for user_id, total in active_counts.items():
        stat = models.StatsUserReservations(user_id=user_id, total_reservations=total)
        db.add(stat)

    db.commit()

    details = {
        "invalidated_reservations": len(affected_ids),
        "stats_users": len(active_counts),
    }

    log_action(
        db,
        actor_id=current_admin.id,
        actor_username=current_admin.username,
        action="integrity_fix",
        resource_type="admin",
        resource_id=None,
        details=str(details),
        success=True,
    )

    if len(affected_ids) > 0:
        send_alert(
            db,
            level="warning",
            message="Rectificación de integridad aplicada",
            payload=details,
        )

    return {"fixed": details, "invalidated_ids": affected_ids}


@router.get("/stats/users/reservations")
def stats_users_reservations(
    db: Session = Depends(get_db),
    current_admin=Depends(require_admin),
) -> List[dict]:
    """Devuelve ranking de usuarios por número de reservas activas registradas en stats."""

    stats = db.query(models.StatsUserReservations).order_by(models.StatsUserReservations.total_reservations.desc()).all()
    return [
        {
            "user_id": s.user_id,
            "total_reservations": s.total_reservations,
            "last_updated": s.last_updated.isoformat() if s.last_updated else None,
        }
        for s in stats
    ]


@router.get("/audit_log")
def get_audit_log(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_admin=Depends(require_admin),
) -> List[dict]:
    entries = (
        db.query(models.AuditLog)
        .order_by(models.AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": e.id,
            "actor_id": e.actor_id,
            "actor_username": e.actor_username,
            "action": e.action,
            "resource_type": e.resource_type,
            "resource_id": e.resource_id,
            "details": e.details,
            "success": e.success,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in entries
    ]


@router.get("/alerts")
def get_alerts(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_admin=Depends(require_admin),
) -> List[dict]:
    entries = (
        db.query(models.Alert)
        .order_by(models.Alert.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": a.id,
            "level": a.level,
            "message": a.message,
            "payload": a.payload,
            "sent": a.sent,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in entries
    ]
