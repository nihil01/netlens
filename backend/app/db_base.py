"""Shared SQLAlchemy declarative base for every NetLens repository."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
