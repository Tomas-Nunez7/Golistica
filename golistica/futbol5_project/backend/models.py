from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Numeric, JSON, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .db import Base
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Numeric

class Role(Base):
    __tablename__ = 'roles'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    email = Column(String)
    role_id = Column(Integer, ForeignKey('roles.id'), nullable=False)
    encrypted_data = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    last_login = Column(DateTime)
    role = relationship('Role')

class Court(Base):
    __tablename__ = 'courts'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    location = Column(String)
    price = Column(Numeric, default=0)
    metadata = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

class Reservation(Base):
    __tablename__ = 'reservations'
    id = Column(Integer, primary_key=True, index=True)
    court_id = Column(Integer, ForeignKey('courts.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'))
    start_ts = Column(String, nullable=False)
    end_ts = Column(String, nullable=False)
    status = Column(String, nullable=False, default='active')
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    version = Column(Integer, default=1)

class AuditLog(Base):
    __tablename__ = 'audit_log'
    id = Column(Integer, primary_key=True, index=True)
    actor_id = Column(Integer, nullable=True)
    actor_username = Column(String, nullable=True)
    action = Column(String, nullable=False)
    resource_type = Column(String)
    resource_id = Column(String)
    details = Column(Text)
    success = Column(Boolean)
    created_at = Column(DateTime, server_default=func.now())

class Alert(Base):
    __tablename__ = 'alerts'
    id = Column(Integer, primary_key=True, index=True)
    level = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    payload = Column(Text)
    sent = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

class StatsUserReservations(Base):
    __tablename__ = 'stats_user_reservations'
    user_id = Column(Integer, primary_key=True)
    total_reservations = Column(Integer, default=0)
    last_updated = Column(DateTime, server_default=func.now())
