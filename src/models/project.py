from typing import List, Optional
from sqlalchemy import String, Text, ForeignKey, Integer, Float, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.models.base import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String, default="general", nullable=False)
    mode: Mapped[str] = mapped_column(String, default="normal", nullable=False)

    chats: Mapped[List["Chat"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    files: Mapped[List["KnowledgeFile"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    pinned: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    tags: Mapped[Optional[dict]] = mapped_column(JSON, default=list)

    project: Mapped["Project"] = relationship(back_populates="chats")


class KnowledgeFile(Base):
    __tablename__ = "knowledge_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, default="knowledge", nullable=False)
    added_at: Mapped[float] = mapped_column(Float, nullable=False)

    project: Mapped["Project"] = relationship(back_populates="files")
