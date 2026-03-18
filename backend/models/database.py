"""
SQLAlchemy ORM models for persisting agent sessions, messages, HITL approvals.
"""
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import (
    Column, String, Text, Float, Boolean, DateTime,
    Integer, ForeignKey, JSON, Enum
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class AgentType(str, PyEnum):
    HR = "hr"
    FINANCE = "finance"
    SUPPORT = "support"
    MANAGER = "manager"


class SessionStatus(str, PyEnum):
    ACTIVE = "active"
    PENDING_APPROVAL = "pending_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    ESCALATED = "escalated"


class HITLStatus(str, PyEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(128), nullable=False, index=True)
    department = Column(String(64))
    status = Column(Enum(SessionStatus), default=SessionStatus.ACTIVE)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, onupdate=lambda: datetime.now(timezone.utc))
    metadata_ = Column("metadata", JSON, default=dict)

    messages = relationship("AgentMessage", back_populates="session", cascade="all, delete-orphan")
    hitl_requests = relationship("HITLRequest", back_populates="session", cascade="all, delete-orphan")


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id = Column(String(36), primary_key=True)
    session_id = Column(String(36), ForeignKey("agent_sessions.id"), nullable=False, index=True)
    agent_type = Column(Enum(AgentType), nullable=False)
    role = Column(String(16), nullable=False)          # "user" | "assistant" | "system" | "tool"
    content = Column(Text, nullable=False)
    tool_calls = Column(JSON, default=list)
    token_count = Column(Integer, default=0)
    latency_ms = Column(Float)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    session = relationship("AgentSession", back_populates="messages")


class HITLRequest(Base):
    __tablename__ = "hitl_requests"

    id = Column(String(36), primary_key=True)
    session_id = Column(String(36), ForeignKey("agent_sessions.id"), nullable=False, index=True)
    agent_type = Column(Enum(AgentType), nullable=False)
    action_type = Column(String(128), nullable=False)
    payload = Column(JSON, nullable=False)
    risk_score = Column(Float, default=0.0)
    status = Column(Enum(HITLStatus), default=HITLStatus.PENDING)
    approver_id = Column(String(128))
    approver_comment = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime)
    expires_at = Column(DateTime)

    session = relationship("AgentSession", back_populates="hitl_requests")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(64), nullable=False, index=True)
    agent_type = Column(String(32))
    session_id = Column(String(36), index=True)
    user_id = Column(String(128))
    action = Column(String(256))
    outcome = Column(String(32))
    risk_score = Column(Float)
    details = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
