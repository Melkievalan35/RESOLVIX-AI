"""initial schema — users, complaints, evidence, policies, agent logs,
fraud assessments, resolutions, workflow states, chat, notifications, audit log

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-08-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("full_name", sa.String(150), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("phone", sa.String(20)),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="customer"),
        sa.Column("is_active", sa.Boolean, server_default=sa.true()),
        sa.Column("is_verified", sa.Boolean, server_default=sa.false()),
        sa.Column("preferred_language", sa.String(10), server_default="en"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_role_active", "users", ["role", "is_active"])

    # --- policies ---
    op.create_table(
        "policies",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("category", sa.String(30)),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("version", sa.String(20), server_default="1.0"),
        sa.Column("is_active", sa.Boolean, server_default=sa.true()),
        sa.Column("vector_collection", sa.String(100)),
        sa.Column("chunk_count", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    # --- complaints ---
    op.create_table(
        "complaints",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("reference_code", sa.String(20), nullable=False, unique=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assigned_agent_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id")),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="submitted"),
        sa.Column("priority", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("order_id", sa.String(100)),
        sa.Column("order_amount", sa.Float),
        sa.Column("sentiment_score", sa.Float),
        sa.Column("confidence_score", sa.Float),
        sa.Column("fraud_risk_score", sa.Float),
        sa.Column("is_auto_resolved", sa.Boolean, server_default=sa.false()),
        sa.Column("sla_due_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime),
        sa.CheckConstraint("fraud_risk_score >= 0 AND fraud_risk_score <= 1", name="ck_fraud_score_range"),
        sa.CheckConstraint("confidence_score >= 0 AND confidence_score <= 1", name="ck_confidence_score_range"),
    )
    op.create_index("ix_complaints_reference_code", "complaints", ["reference_code"])
    op.create_index("ix_complaints_status_priority", "complaints", ["status", "priority"])
    op.create_index("ix_complaints_customer_created", "complaints", ["customer_id", "created_at"])

    # --- evidence ---
    op.create_table(
        "evidence",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("complaint_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("complaints.id"), nullable=False),
        sa.Column("evidence_type", sa.String(20), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_size_kb", sa.Integer),
        sa.Column("ai_analysis", postgresql.JSONB),
        sa.Column("extracted_text", sa.Text),
        sa.Column("damage_detected", sa.Boolean),
        sa.Column("authenticity_score", sa.Float),
        sa.Column("uploaded_at", sa.DateTime, server_default=sa.func.now()),
    )

    # --- agent_execution_logs ---
    op.create_table(
        "agent_execution_logs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("complaint_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("complaints.id"), nullable=False),
        sa.Column("agent_name", sa.String(30), nullable=False),
        sa.Column("input_summary", sa.Text),
        sa.Column("output_summary", sa.Text),
        sa.Column("reasoning", sa.Text),
        sa.Column("confidence", sa.Float),
        sa.Column("retrieved_policy_chunks", postgresql.JSONB),
        sa.Column("tool_calls", postgresql.JSONB),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("status", sa.String(20), server_default="success"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_agentlog_complaint_agent", "agent_execution_logs", ["complaint_id", "agent_name"])

    # --- fraud_assessments ---
    op.create_table(
        "fraud_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("complaint_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("complaints.id"), nullable=False, unique=True),
        sa.Column("risk_score", sa.Float, nullable=False),
        sa.Column("risk_level", sa.String(20), nullable=False),
        sa.Column("anomaly_flags", postgresql.JSONB),
        sa.Column("behavioral_flags", postgresql.JSONB),
        sa.Column("is_flagged_for_manual_review", sa.Boolean, server_default=sa.false()),
        sa.Column("model_version", sa.String(50)),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    # --- resolutions ---
    op.create_table(
        "resolutions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("complaint_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("complaints.id"), nullable=False, unique=True),
        sa.Column("decision", sa.String(50), nullable=False),
        sa.Column("resolution_amount", sa.Float),
        sa.Column("justification", sa.Text, nullable=False),
        sa.Column("policy_citations", postgresql.JSONB),
        sa.Column("requires_human_approval", sa.Boolean, server_default=sa.false()),
        sa.Column("approved_by_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("finalized_at", sa.DateTime),
    )

    # --- workflow_states ---
    op.create_table(
        "workflow_states",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("complaint_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("complaints.id"), nullable=False, unique=True),
        sa.Column("current_node", sa.String(50), nullable=False, server_default="intake"),
        sa.Column("graph_state", postgresql.JSONB),
        sa.Column("retry_count", sa.Integer, server_default="0"),
        sa.Column("last_error", sa.Text),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    # --- chat_messages ---
    op.create_table(
        "chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("complaint_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("complaints.id")),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("sender", sa.String(20), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("intent", sa.String(50)),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_chat_created", "chat_messages", ["created_at"])

    # --- notifications ---
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("complaint_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("complaints.id")),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("is_read", sa.Boolean, server_default=sa.false()),
        sa.Column("sent_at", sa.DateTime, server_default=sa.func.now()),
    )

    # --- audit_logs ---
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id")),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.String(100), nullable=False),
        sa.Column("before_state", postgresql.JSONB),
        sa.Column("after_state", postgresql.JSONB),
        sa.Column("ip_address", sa.String(50)),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_auditlog_entity", "audit_logs", ["entity_type", "entity_id"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("notifications")
    op.drop_table("chat_messages")
    op.drop_table("workflow_states")
    op.drop_table("resolutions")
    op.drop_table("fraud_assessments")
    op.drop_table("agent_execution_logs")
    op.drop_table("evidence")
    op.drop_table("complaints")
    op.drop_table("policies")
    op.drop_table("users")
