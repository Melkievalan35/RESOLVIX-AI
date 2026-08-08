"""
models.py
---------
SQLAlchemy ORM models for RESOLVIX-AI.

Domain covered:
    - Users (customers, admins, agents)
    - Complaints (the core entity the whole platform revolves around)
    - Evidence (images/invoices attached to a complaint)
    - Policies (source docs for the RAG knowledge base)
    - AgentExecutionLog (every AI agent's decision — powers explainability)
    - FraudAssessment (fraud_agent output)
    - Resolution (resolution_agent output)
    - WorkflowState (workflow_agent's state machine tracking)
    - Notification
    - AuditLog (immutable, for compliance)
    - ChatMessage (customer <-> AI conversation transcript)

Import Base + engine from backend/database/connection.py — do not
redefine Base here, so both files stay on one metadata registry.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey,
    Enum as SAEnum, JSON, Index, UniqueConstraint, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database.connection import Base


def gen_uuid():
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Enums — kept centralized so API + AI layer share the same vocabulary
# ---------------------------------------------------------------------------
class UserRole(str, enum.Enum):
    CUSTOMER = "customer"

    # Existing
    SUPPORT_AGENT = "support_agent"

    # Alias used by the API
    AGENT = "support_agent"

    ADMIN = "admin"

    # Existing
    SUPER_ADMIN = "super_admin"

    # Alias used by some modules
    AUDITOR = "auditor"

class ComplaintStatus(str, enum.Enum):
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"          # evidence/policy agents working
    FRAUD_CHECK = "fraud_check"
    AWAITING_CUSTOMER = "awaiting_customer"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    REJECTED = "rejected"
    CLOSED = "closed"


class ComplaintPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ComplaintCategory(str, enum.Enum):
    REFUND = "refund"
    WARRANTY = "warranty"
    DAMAGED_PRODUCT = "damaged_product"
    DELIVERY_ISSUE = "delivery_issue"
    BILLING = "billing"
    SERVICE_QUALITY = "service_quality"
    OTHER = "other"


class EvidenceType(str, enum.Enum):
    IMAGE = "image"
    INVOICE = "invoice"
    VIDEO = "video"
    DOCUMENT = "document"


class AgentName(str, enum.Enum):
    CUSTOMER_AGENT = "customer_agent"
    EVIDENCE_AGENT = "evidence_agent"
    POLICY_AGENT = "policy_agent"
    FRAUD_AGENT = "fraud_agent"
    RESOLUTION_AGENT = "resolution_agent"
    WORKFLOW_AGENT = "workflow_agent"
    ESCALATION_AGENT = "escalation_agent"
    LEARNING_AGENT = "learning_agent"
    ORCHESTRATOR = "orchestrator"


class NotificationChannel(str, enum.Enum):
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    IN_APP = "in_app"
    WHATSAPP = "whatsapp"


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    full_name = Column(String(150), nullable=False)
    email = Column(String(255), nullable=False, unique=True, index=True)
    phone = Column(String(20), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(SAEnum(UserRole), nullable=False, default=UserRole.CUSTOMER)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    preferred_language = Column(String(10), default="en")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    complaints = relationship("Complaint", back_populates="customer", foreign_keys="Complaint.customer_id")
    audit_logs = relationship("AuditLog", back_populates="actor")

    __table_args__ = (
        Index("ix_users_role_active", "role", "is_active"),
    )


# ---------------------------------------------------------------------------
# Complaints — the core entity
# ---------------------------------------------------------------------------
class Complaint(Base):
    __tablename__ = "complaints"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    reference_code = Column(String(20), nullable=False, unique=True, index=True)  # e.g. RSX-2026-000123

    customer_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    assigned_agent_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)

    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(SAEnum(ComplaintCategory), nullable=False)
    status = Column(SAEnum(ComplaintStatus), nullable=False, default=ComplaintStatus.SUBMITTED, index=True)
    priority = Column(SAEnum(ComplaintPriority), nullable=False, default=ComplaintPriority.MEDIUM)

    order_id = Column(String(100), nullable=True)
    order_amount = Column(Float, nullable=True)

    sentiment_score = Column(Float, nullable=True)        # -1.0 to 1.0, from sentiment_analysis.py
    confidence_score = Column(Float, nullable=True)        # AI resolution confidence, 0-1
    fraud_risk_score = Column(Float, nullable=True)        # 0-1, from fraud_agent

    is_auto_resolved = Column(Boolean, default=False)
    sla_due_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)

    customer = relationship("User", back_populates="complaints", foreign_keys=[customer_id])
    evidence_items = relationship("Evidence", back_populates="complaint", cascade="all, delete-orphan")
    agent_logs = relationship("AgentExecutionLog", back_populates="complaint", cascade="all, delete-orphan")
    fraud_assessment = relationship("FraudAssessment", back_populates="complaint", uselist=False, cascade="all, delete-orphan")
    resolution = relationship("Resolution", back_populates="complaint", uselist=False, cascade="all, delete-orphan")
    workflow_state = relationship("WorkflowState", back_populates="complaint", uselist=False, cascade="all, delete-orphan")
    chat_messages = relationship("ChatMessage", back_populates="complaint", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="complaint", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_complaints_status_priority", "status", "priority"),
        Index("ix_complaints_customer_created", "customer_id", "created_at"),
        CheckConstraint("fraud_risk_score >= 0 AND fraud_risk_score <= 1", name="ck_fraud_score_range"),
        CheckConstraint("confidence_score >= 0 AND confidence_score <= 1", name="ck_confidence_score_range"),
    )


# ---------------------------------------------------------------------------
# Evidence (images, invoices, videos attached to a complaint)
# ---------------------------------------------------------------------------
class Evidence(Base):
    __tablename__ = "evidence"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    complaint_id = Column(UUID(as_uuid=False), ForeignKey("complaints.id"), nullable=False)

    evidence_type = Column(SAEnum(EvidenceType), nullable=False)
    file_path = Column(String(500), nullable=False)       # storage/complaint_images/... or storage/invoices/...
    file_name = Column(String(255), nullable=False)
    file_size_kb = Column(Integer, nullable=True)

    # Populated by ai/vision and ai/ocr modules
    ai_analysis = Column(JSON, nullable=True)              # damage_detector / image_classifier output
    extracted_text = Column(Text, nullable=True)            # OCR output for invoices
    damage_detected = Column(Boolean, nullable=True)
    authenticity_score = Column(Float, nullable=True)       # tamper-detection confidence, 0-1

    uploaded_at = Column(DateTime, default=datetime.utcnow)

    complaint = relationship("Complaint", back_populates="evidence_items")


# ---------------------------------------------------------------------------
# Policies — source documents chunked/embedded for the RAG pipeline
# ---------------------------------------------------------------------------
class Policy(Base):
    __tablename__ = "policies"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    title = Column(String(200), nullable=False)
    category = Column(SAEnum(ComplaintCategory), nullable=True)
    file_path = Column(String(500), nullable=False)         # data/policies/*.pdf
    version = Column(String(20), default="1.0")
    is_active = Column(Boolean, default=True)

    # Vector store pointer — actual vectors live in data/vector_store (Chroma/FAISS/Pinecone),
    # this column stores the collection/namespace + chunk count for traceability.
    vector_collection = Column(String(100), nullable=True)
    chunk_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# Agent Execution Log — powers the explainable_ai module + audit trail
# ---------------------------------------------------------------------------
class AgentExecutionLog(Base):
    __tablename__ = "agent_execution_logs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    complaint_id = Column(UUID(as_uuid=False), ForeignKey("complaints.id"), nullable=False)

    agent_name = Column(SAEnum(AgentName), nullable=False)
    input_summary = Column(Text, nullable=True)
    output_summary = Column(Text, nullable=True)
    reasoning = Column(Text, nullable=True)                 # human-readable chain-of-reasoning
    confidence = Column(Float, nullable=True)
    retrieved_policy_chunks = Column(JSON, nullable=True)   # citations used by RAG generator
    tool_calls = Column(JSON, nullable=True)                # structured record of tool/function calls
    latency_ms = Column(Integer, nullable=True)
    status = Column(String(20), default="success")          # success | failed | retried

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    complaint = relationship("Complaint", back_populates="agent_logs")

    __table_args__ = (
        Index("ix_agentlog_complaint_agent", "complaint_id", "agent_name"),
    )


# ---------------------------------------------------------------------------
# Fraud Assessment — fraud_agent's structured verdict
# ---------------------------------------------------------------------------
class FraudAssessment(Base):
    __tablename__ = "fraud_assessments"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    complaint_id = Column(UUID(as_uuid=False), ForeignKey("complaints.id"), nullable=False, unique=True)

    risk_score = Column(Float, nullable=False)               # 0-1
    risk_level = Column(String(20), nullable=False)          # low | medium | high
    anomaly_flags = Column(JSON, nullable=True)               # ["duplicate_claim", "image_reuse", ...]
    behavioral_flags = Column(JSON, nullable=True)
    is_flagged_for_manual_review = Column(Boolean, default=False)
    model_version = Column(String(50), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    complaint = relationship("Complaint", back_populates="fraud_assessment")


# ---------------------------------------------------------------------------
# Resolution — resolution_agent's final decision
# ---------------------------------------------------------------------------
class Resolution(Base):
    __tablename__ = "resolutions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    complaint_id = Column(UUID(as_uuid=False), ForeignKey("complaints.id"), nullable=False, unique=True)

    decision = Column(String(50), nullable=False)             # approved | rejected | partial_refund | replacement
    resolution_amount = Column(Float, nullable=True)
    justification = Column(Text, nullable=False)               # cites policy clauses
    policy_citations = Column(JSON, nullable=True)
    requires_human_approval = Column(Boolean, default=False)
    approved_by_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    finalized_at = Column(DateTime, nullable=True)

    complaint = relationship("Complaint", back_populates="resolution")


# ---------------------------------------------------------------------------
# Workflow State — tracks the LangGraph state machine per complaint
# ---------------------------------------------------------------------------
class WorkflowState(Base):
    __tablename__ = "workflow_states"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    complaint_id = Column(UUID(as_uuid=False), ForeignKey("complaints.id"), nullable=False, unique=True)

    current_node = Column(String(50), nullable=False, default="intake")
    graph_state = Column(JSON, nullable=True)                  # full LangGraph checkpoint snapshot
    retry_count = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    complaint = relationship("Complaint", back_populates="workflow_state")


# ---------------------------------------------------------------------------
# Chat Messages — customer <-> AI conversation transcript
# ---------------------------------------------------------------------------
class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    complaint_id = Column(UUID(as_uuid=False), ForeignKey("complaints.id"), nullable=True)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)

    sender = Column(String(20), nullable=False)                # "customer" | "ai" | "agent"
    message = Column(Text, nullable=False)
    intent = Column(String(50), nullable=True)                  # classified intent from customer_agent
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    complaint = relationship("Complaint", back_populates="chat_messages")


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    complaint_id = Column(UUID(as_uuid=False), ForeignKey("complaints.id"), nullable=True)

    channel = Column(SAEnum(NotificationChannel), nullable=False)
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    sent_at = Column(DateTime, default=datetime.utcnow)

    complaint = relationship("Complaint", back_populates="notifications")


# ---------------------------------------------------------------------------
# Audit Log — immutable compliance trail (never updated, only inserted)
# ---------------------------------------------------------------------------
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    actor_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)  # null = system/AI action
    action = Column(String(100), nullable=False)                # "complaint.status_changed", "fraud.flagged"
    entity_type = Column(String(50), nullable=False)             # "complaint", "user", "resolution"
    entity_id = Column(String(100), nullable=False)
    before_state = Column(JSON, nullable=True)
    after_state = Column(JSON, nullable=True)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    actor = relationship("User", back_populates="audit_logs")

    __table_args__ = (
        Index("ix_auditlog_entity", "entity_type", "entity_id"),
    )
# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

class Report(Base):
    __tablename__ = "reports"

    id = Column(String, primary_key=True, default=gen_uuid)

    requested_by = Column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    report_type = Column(String(50), nullable=False)

    date_from = Column(DateTime, nullable=True)

    date_to = Column(DateTime, nullable=True)

    status = Column(String(20), default="pending", nullable=False)

    file_path = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    requester = relationship("User")
