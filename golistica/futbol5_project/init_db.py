# -*- coding: utf-8 -*-
from backend.db import Base, motor
Base.metadata.create_all(bind=motor)
print('Base de datos inicializada correctamente')
