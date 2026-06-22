from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Integer, String, Text, Float, DateTime,
    ForeignKey, Boolean, Enum as SAEnum, Table, Column
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
import enum

from app.database import Base


class UserRole(str, enum.Enum):
    admin = "admin"
    faculty = "faculty"


class OutputType(str, enum.Enum):
    yayin = "Makale/Yayın"
    bildiri = "Bildiri"
    patent = "Patent"
    faydali_model = "Faydalı Model"
    kitap = "Kitap/Kitap Bölümü"
    tez = "Tez"
    yazilim = "Yazılım"
    prototip = "Ürün/Prototip"
    sergi = "Sergi"
    odul = "Ödül"
    isbirligi = "İş Birliği"
    diger = "Diğer"


class OutputStatus(str, enum.Enum):
    taslak = "Taslak"
    gonderildi = "Gönderildi"
    onaylandi = "Onaylandı"
    revize_istendi = "Revize İstendi"


# Proje — Araştırmacı çoka-çok ilişki tablosu
project_researchers = Table(
    "project_researchers",
    Base.metadata,
    Column("project_id", Integer, ForeignKey("projects.id")),
    Column("user_id", Integer, ForeignKey("users.id")),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(200), unique=True, nullable=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole), default=UserRole.faculty, nullable=False)
    faculty: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    department: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    led_projects: Mapped[list["Project"]] = relationship("Project", back_populates="principal_investigator")
    research_projects: Mapped[list["Project"]] = relationship(
        "Project", secondary=project_researchers, back_populates="researchers"
    )
    outputs: Mapped[list["Output"]] = relationship("Output", back_populates="submitted_by")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    budget: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    department: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    project_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    application_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    no_output_declared: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    principal_investigator_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    principal_investigator: Mapped[Optional["User"]] = relationship("User", back_populates="led_projects")
    researchers: Mapped[list["User"]] = relationship(
        "User", secondary=project_researchers, back_populates="research_projects"
    )
    outputs: Mapped[list["Output"]] = relationship("Output", back_populates="project", cascade="all, delete-orphan")


class Output(Base):
    __tablename__ = "outputs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"), nullable=False)
    submitted_by_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)

    output_type: Mapped[OutputType] = mapped_column(SAEnum(OutputType), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    authors: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    publication_date: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    identifier: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    publisher_venue: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    acknowledgement_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    relation_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[OutputStatus] = mapped_column(SAEnum(OutputStatus), default=OutputStatus.taslak)
    admin_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    web_visible: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project: Mapped["Project"] = relationship("Project", back_populates="outputs")
    submitted_by: Mapped["User"] = relationship("User", back_populates="outputs")
    attachments: Mapped[list["Attachment"]] = relationship("Attachment", back_populates="output", cascade="all, delete-orphan")


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    output_id: Mapped[int] = mapped_column(Integer, ForeignKey("outputs.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    output: Mapped["Output"] = relationship("Output", back_populates="attachments")


class LoginToken(Base):
    __tablename__ = "login_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship("User")
