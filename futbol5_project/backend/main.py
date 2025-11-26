"""Backend simplificado para Golística.

Usa los modelos reales definidos en models.py (Court, Reservation) y expone
endpoints para listar canchas, filtrarlas por zona/barrio y sembrar datos
de ejemplo de Buenos Aires.
"""

from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .db import SessionLocal, motor, Base
from . import models, schemas


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
def create_court(payload: schemas.CourtIn, db: Session = Depends(get_db)):
    """Crea una nueva cancha."""

    court = models.Court(
        name=payload.name,
        location=payload.location,
        price=payload.price or 0.0,
    )
    db.add(court)
    db.commit()
    db.refresh(court)
    return {"id": court.id}


@app.post("/api/courts/seed_buenos_aires", status_code=201)
def seed_courts_buenos_aires(db: Session = Depends(get_db)):
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
    return {"created": creadas}


@app.post("/api/reservations", status_code=201)
def create_reservation(payload: schemas.ReservationIn, db: Session = Depends(get_db)):
    """Crea una reserva simple sin validaciones complejas de usuario.

    Nota: Esta versión mínima no valida solapamientos ni usuarios; sirve
    solo como demo para el flujo de reservas.
    """

    # Validar que la cancha exista
    court = db.query(models.Court).filter(models.Court.id == payload.court_id).first()
    if not court:
        raise HTTPException(status_code=404, detail="Cancha no encontrada")

    reservation = models.Reservation(
        court_id=payload.court_id,
        user_id=None,
        start_ts=payload.start_ts,
        end_ts=payload.end_ts,
        status="active",
    )
    db.add(reservation)
    db.commit()
    db.refresh(reservation)
    return {"id": reservation.id}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
