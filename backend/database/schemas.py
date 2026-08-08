"""
schema.py
---------
Pydantic v2 schemas — the contract between backend/api/*.py, ai/agents/*.py,
and the frontend. Keeping these separate from models.py means the DB layer
can evolve without breaking the API contract, and vice versa.

Naming convention:
    <Entity>Base    -> shared fields
    <Entity>Create  -> inbound payload (POST)
    <Entity>Update  -> inbound partial payload (PATCH)
    <Entity>Out     -> outbound response (includes id, timestamps)
"""

from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, EmailStr, Field, ConfigDict

from database.models import (
    UserRole, ComplaintStatus, ComplaintPriority, ComplaintCategory,
    EvidenceType, AgentName, NotificationChannel,
)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
class UserBase(BaseModel):
    full_name: str = Field(..., max_length=150)
    email: EmailStr
    phone: Optional[str] = None
    preferred_language: str = "en"


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)
    role: UserRole = UserRole.CUSTOMER


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    preferred_language: Optional[str] = None
    is_active: Optional[bool] = None


class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    role: UserRole
    is_active: bool
    is_verified: bool
    created_at: datetime


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    refresh_token: str = ""
    token_type: str = "bearer"
    expires_in: int = 1800
    user: UserOut


class TokenData(BaseModel):
    email: str | None = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------
class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    evidence_type: EvidenceType
    file_path: str
    file_name: str
    ai_analysis: Optional[Dict[str, Any]] = None
    extracted_text: Optional[str] = None
    damage_detected: Optional[bool] = None
    authenticity_score: Optional[float] = None
    uploaded_at: datetime

# ---------------------------------------------------------------------------
# Audit Logs
# ---------------------------------------------------------------------------

class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    action: str
    entity_type: str
    entity_id: str | None = None
    performed_by: str | None = None
    details: dict | None = None
    created_at: datetime



# ---------------------------------------------------------------------------
# Complaints
# ---------------------------------------------------------------------------
class ComplaintBase(BaseModel):
    title: str = Field(..., max_length=200)
    description: str
    category: ComplaintCategory
    order_id: Optional[str] = None
    order_amount: Optional[float] = None


class ComplaintCreate(ComplaintBase):
    pass


class ComplaintUpdate(BaseModel):
    status: Optional[ComplaintStatus] = None
    priority: Optional[ComplaintPriority] = None
    assigned_agent_id: Optional[str] = None


class ComplaintOut(ComplaintBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    reference_code: str
    customer_id: str
    status: ComplaintStatus
    priority: ComplaintPriority
    sentiment_score: Optional[float] = None
    confidence_score: Optional[float] = None
    fraud_risk_score: Optional[float] = None
    is_auto_resolved: bool
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None


class ComplaintDetailOut(ComplaintOut):
    """Full detail view — used on the complaint detail / admin drill-down screens."""
    evidence_items: List[EvidenceOut] = []
    agent_logs: List["AgentExecutionLogOut"] = []
    fraud_assessment: Optional["FraudAssessmentOut"] = None
    resolution: Optional["ResolutionOut"] = None


# ---------------------------------------------------------------------------
# Agent Execution Logs (explainability)
# ---------------------------------------------------------------------------
class AgentExecutionLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    agent_name: AgentName
    input_summary: Optional[str] = None
    output_summary: Optional[str] = None
    reasoning: Optional[str] = None
    confidence: Optional[float] = None
    retrieved_policy_chunks: Optional[List[Dict[str, Any]]] = None
    latency_ms: Optional[int] = None
    status: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Fraud
# ---------------------------------------------------------------------------
class FraudAssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    risk_score: float
    risk_level: str
    anomaly_flags: Optional[List[str]] = None
    behavioral_flags: Optional[List[str]] = None
    is_flagged_for_manual_review: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------
class ResolutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    decision: str
    resolution_amount: Optional[float] = None
    justification: str
    policy_citations: Optional[List[Dict[str, Any]]] = None
    requires_human_approval: bool
    created_at: datetime
    finalized_at: Optional[datetime] = None


class ResolutionApproval(BaseModel):
    approved: bool
    override_amount: Optional[float] = None
    approver_notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------
class ChatMessageIn(BaseModel):
    complaint_id: Optional[str] = None
    message: str = Field(..., min_length=1, max_length=4000)


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    sender: str
    message: str
    intent: Optional[str] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    channel: NotificationChannel
    title: str
    body: str
    is_read: bool
    sent_at: datetime


# ---------------------------------------------------------------------------
# Dashboard / Reports (aggregate response shapes — not tied 1:1 to a table)
# ---------------------------------------------------------------------------

class DashboardSummary(BaseModel):
    total_complaints: int
    open_complaints: int
    resolved_today: int
    avg_resolution_time_hours: float
    auto_resolution_rate: float
    avg_fraud_risk_score: float
    sla_breaches: int


class StatusCount(BaseModel):
    status: ComplaintStatus
    count: int


class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[Any]


class PaginatedComplaints(PaginatedResponse):
    items: List[ComplaintOut]


# Resolve forward references used in ComplaintDetailOut
ComplaintDetailOut.model_rebuild()
# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

class ReportRequest(BaseModel):
    report_type: str
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    requested_by: str
    report_type: str
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    status: str
    file_path: Optional[str] = None
    created_at: datetime