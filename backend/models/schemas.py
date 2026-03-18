"""
Pydantic schemas for API request/response validation.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from backend.models.database import AgentType, HITLStatus, SessionStatus


# ── Common ───────────────────────────────────────────────────────────────────
class BaseResponse(BaseModel):
    success: bool = True
    message: str = "OK"


# ── Chat ─────────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    user_id: str = Field(..., description="Unique user identifier")
    session_id: Optional[str] = Field(None, description="Existing session ID (optional)")
    message: str = Field(..., min_length=1, max_length=4096)
    department: Optional[str] = Field(None, description="User department hint for routing")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentStep(BaseModel):
    agent: AgentType
    input: str
    output: str
    tool_calls: List[Dict] = []
    latency_ms: float = 0.0


class ChatResponse(BaseModel):
    session_id: str
    response: str
    agent_type: AgentType
    steps: List[AgentStep] = []
    hitl_required: bool = False
    hitl_request_id: Optional[str] = None
    sources: List[Dict[str, str]] = []
    confidence: float = 1.0
    created_at: datetime


# ── Session ───────────────────────────────────────────────────────────────────
class SessionSummary(BaseModel):
    id: str
    user_id: str
    department: Optional[str]
    status: SessionStatus
    message_count: int
    created_at: datetime
    updated_at: Optional[datetime]


class SessionHistory(BaseModel):
    session: SessionSummary
    messages: List[Dict[str, Any]]


# ── HITL ─────────────────────────────────────────────────────────────────────
class HITLApprovalRequest(BaseModel):
    hitl_id: str
    decision: HITLStatus  # APPROVED | REJECTED
    approver_id: str
    comment: Optional[str] = None


class HITLDetail(BaseModel):
    id: str
    session_id: str
    agent_type: AgentType
    action_type: str
    payload: Dict[str, Any]
    risk_score: float
    status: HITLStatus
    created_at: datetime
    expires_at: Optional[datetime]


# ── Metrics ───────────────────────────────────────────────────────────────────
class MetricsResponse(BaseModel):
    agent_calls: Dict[str, int]
    errors: Dict[str, int]
    avg_latencies: Dict[str, float]
    hitl_events: int
    uptime_seconds: float


# ── Documents ────────────────────────────────────────────────────────────────
class IngestRequest(BaseModel):
    source_type: str = Field(..., pattern="^(pdf|csv|database)$")
    source_path: str
    agent_scope: List[AgentType]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class IngestResponse(BaseResponse):
    chunks_indexed: int
    source: str
