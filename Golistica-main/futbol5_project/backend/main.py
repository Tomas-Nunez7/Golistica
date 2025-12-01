"""Backend simplificado para Golística.

Usa los modelos reales definidos en models.py (Court, Reservation) y expone
endpoints para listar canchas, filtrarlas por zona/barrio y sembrar datos
de ejemplo de Buenos Aires.
"""

from typing import List, Optional
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .db import SessionLocal, motor, Base
from . import models, schemas
from .auth import router as auth_router, require_operator_or_admin, require_admin, require_user
from .admin_routes import router as admin_router
from .audit import log_action, send_alert


# Crear tablas en la base de datos (si no existen)
Base.metadata.create_all(bind=motor)


app = FastAPI(title="Golística - API de Reservas")


# Habilitar CORS para permitir llamadas desde el frontend (file:// o http://localhost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En desarrollo permitimos todo
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Registrar routers (autenticación y administración)
app.include_router(auth_router)
app.include_router(admin_router)


def get_db():
    """Dependencia para obtener una sesión de base de datos."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/api/courts", response_model=List[dict])
def list_courts(
    zona: Optional[str] = Query(None, description="Zona o barrio para filtrar"),
    db: Session = Depends(get_db),
):
    """Obtiene la lista de canchas, opcionalmente filtradas por zona/barrio."""

    query = db.query(models.Court)

    if zona:
        patron = f"%{zona}%"
        query = query.filter(models.Court.location.ilike(patron))

    courts = query.order_by(models.Court.name.asc()).all()

    return [
        {
            "id": c.id,
            "name": c.name,
            "location": c.location,
            "price": float(c.price) if c.price is not None else 0.0,
        }
        for c in courts
    ]


@app.post("/api/courts", status_code=201)
def create_court(
    payload: schemas.CourtIn,
    db: Session = Depends(get_db),
    current_user=Depends(require_operator_or_admin),
):
    """Crea una nueva cancha."""

    court = models.Court(
        name=payload.name,
        location=payload.location,
        price=payload.price or 0.0,
    )
    db.add(court)
    db.commit()
    db.refresh(court)
    log_action(
        db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action="create_court",
        resource_type="court",
        resource_id=str(court.id),
        details=f"Creación de cancha {court.name}",
        success=True,
    )
    return {"id": court.id}


@app.post("/api/courts/seed_buenos_aires", status_code=201)
def seed_courts_buenos_aires(
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    """Crea varias canchas de ejemplo en distintos barrios de Buenos Aires.

    Este endpoint es idempotente: si una cancha con mismo nombre ya existe,
    no se vuelve a crear.
    """

    ejemplos = [
        {"name": "Gol Palermo 1", "location": "Palermo", "price": 12000},
        {"name": "Gol Palermo 2", "location": "Palermo", "price": 13000},
        {"name": "Caballito F5", "location": "Caballito", "price": 11000},
        {"name": "Caballito Parque", "location": "Caballito", "price": 11500},
        {"name": "Almagro Futbol", "location": "Almagro", "price": 10000},
        {"name": "Flores Sport", "location": "Flores", "price": 10500},
        {"name": "Belgrano Norte", "location": "Belgrano", "price": 14000},
        {"name": "Belgrano Río", "location": "Belgrano", "price": 14500},
        {"name": "Recoleta Arena", "location": "Recoleta", "price": 15000},
        {"name": "San Telmo Futbol 5", "location": "San Telmo", "price": 9500},
    ]

    creadas = 0
    for e in ejemplos:
        existe = (
            db.query(models.Court)
            .filter(models.Court.name == e["name"], models.Court.location == e["location"])
            .first()
        )
        if existe:
            continue

        court = models.Court(name=e["name"], location=e["location"], price=e["price"])
        db.add(court)
        creadas += 1

    db.commit()
    log_action(
        db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action="seed_courts",
        resource_type="court",
        resource_id=None,
        details=f"Seed de canchas Buenos Aires, creadas={creadas}",
        success=True,
    )
    return {"created": creadas}


@app.post("/api/reservations", status_code=201)
def create_reservation(
    payload: schemas.ReservationIn,
    db: Session = Depends(get_db),
    current_user=Depends(require_user),
):
    """Crea una reserva controlando solapamientos para la misma cancha.

    Si existe otra reserva activa que se solape en el intervalo solicitado,
    devuelve 409 Conflict.
    """

    # Validar que la cancha exista
    court = db.query(models.Court).filter(models.Court.id == payload.court_id).first()
    if not court:
        log_action(
            db,
            actor_id=current_user.id,
            actor_username=current_user.username,
            action="reservation_court_not_found",
            resource_type="reservation",
            resource_id=None,
            details=f"Cancha {payload.court_id} inexistente",
            success=False,
        )
        send_alert(
            db,
            level="error",
            message="Intento de reserva sobre cancha inexistente",
            payload={"court_id": payload.court_id, "user_id": current_user.id},
        )
        raise HTTPException(status_code=404, detail="Cancha no encontrada")

    # Comprobar solapamientos con reservas existentes
    existing_reservations = (
        db.query(models.Reservation)
        .filter(
            models.Reservation.court_id == payload.court_id,
            models.Reservation.status == "active",
        )
        .all()
    )

    try:
        new_start = datetime.fromisoformat(payload.start_ts)
        new_end = datetime.fromisoformat(payload.end_ts)
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de fecha/hora inválido. Use ISO 8601.")

    for r in existing_reservations:
        try:
            r_start = datetime.fromisoformat(r.start_ts)
            r_end = datetime.fromisoformat(r.end_ts)
        except ValueError:
            continue

        # Solapamiento si no se cumple (nuevo termina antes o empieza después)
        if not (new_end <= r_start or new_start >= r_end):
            log_action(
                db,
                actor_id=current_user.id,
                actor_username=current_user.username,
                action="reservation_conflict",
                resource_type="reservation",
                resource_id=str(r.id),
                details=f"Conflicto con reserva existente {r.id} en cancha {r.court_id}",
                success=False,
            )
            send_alert(
                db,
                level="warning",
                message="Conflicto de reserva detectado",
                payload={
                    "court_id": payload.court_id,
                    "user_id": current_user.id,
                    "existing_reservation_id": r.id,
                },
            )
            raise HTTPException(status_code=409, detail="Ya existe una reserva para esa cancha y horario")

    reservation = models.Reservation(
        court_id=payload.court_id,
        user_id=current_user.id,
        start_ts=payload.start_ts,
        end_ts=payload.end_ts,
        status="active",
    )
    db.add(reservation)
    db.commit()
    db.refresh(reservation)
    log_action(
        db,
        actor_id=current_user.id,
        actor_username=current_user.username,
        action="create_reservation",
        resource_type="reservation",
        resource_id=str(reservation.id),
        details=f"Reserva sobre cancha {reservation.court_id}",
        success=True,
    )
    return {"id": reservation.id}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
