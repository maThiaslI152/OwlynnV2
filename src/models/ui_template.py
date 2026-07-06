import time
from sqlalchemy import Column, String, Float
from src.models.base import Base

# We'll use a JSON type that is compatible with both SQLite and Postgres
from sqlalchemy.types import JSON


class UITemplate(Base):
    __tablename__ = "ui_templates"

    id = Column(String, primary_key=True)
    type = Column(String, nullable=False)
    payload = Column(JSON, nullable=False)
    created_at = Column(Float, default=time.time)
