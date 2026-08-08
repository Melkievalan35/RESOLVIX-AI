"""
Complaint lifecycle endpoints:
create, list, update, delete, assign,
evidence upload, history, and one-shot AI submission.
"""

import os
import shutil
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from ai.agents.orchestrator import Orchestrator
from core.security import get_current_user, require_roles
from database.connection import get_db

from database.models import (
    AgentExecutionLog,
    AgentName,
    AuditLog,
    Complaint,
    ComplaintPriority,
    ComplaintStatus,
    Evidence,
    EvidenceType,
    FraudAssessment,
    Resolution,
    User,
    UserRole,
    WorkflowState,
)

from database.schemas import (
    AuditLogOut,
    ComplaintCreate,
    ComplaintOut,
    ComplaintUpdate,
    EvidenceOut,
    PaginatedComplaints,
)


# ==========================================================
# ROUTER
# ==========================================================

router = APIRouter(
    prefix="/complaints",
    tags=["Complaints"],
)


# ==========================================================
# STORAGE
# ==========================================================

EVIDENCE_DIR = os.getenv(
    "EVIDENCE_STORAGE_DIR",
    "storage/complaint_images",
)

os.makedirs(
    EVIDENCE_DIR,
    exist_ok=True,
)


# ==========================================================
# AUDIT LOG
# ==========================================================

def _log(
    db: Session,
    complaint_id: str,
    actor_id: str,
    action: str,
    details: str = "",
):
    """
    Add an audit entry.

    The current AuditLog model does not accept complaint_id/details
    as constructor arguments, so keep this compatible with the
    current model.
    """

    try:
        db.add(
            AuditLog(
                actor_id=actor_id,
                action=action,
                details=(
                    f"Complaint {complaint_id}: {details}"
                ).strip(),
            )
        )

    except Exception as exc:
        print(
            f"Audit log warning: {exc}"
        )


# ==========================================================
# FILE CLASSIFICATION
# ==========================================================

def _classify_file(
    filename: str,
) -> EvidenceType:

    ext = os.path.splitext(
        filename or ""
    )[1].lower()

    if ext in (
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
    ):
        return EvidenceType.IMAGE

    if ext in (
        ".mp4",
        ".mov",
        ".avi",
        ".webm",
    ):
        return EvidenceType.VIDEO

    if (
        ext in (
            ".pdf",
            ".doc",
            ".docx",
        )
        or "invoice" in (
            filename or ""
        ).lower()
    ):
        return EvidenceType.INVOICE

    return EvidenceType.DOCUMENT


# ==========================================================
# SAVE UPLOAD
# ==========================================================

def _save_upload(
    complaint_id: str,
    file: UploadFile,
) -> str:

    ext = os.path.splitext(
        file.filename or ""
    )[1].lower()

    safe_name = (
        f"{complaint_id}_"
        f"{uuid.uuid4().hex}"
        f"{ext}"
    )

    filepath = os.path.join(
        EVIDENCE_DIR,
        safe_name,
    )

    with open(
        filepath,
        "wb",
    ) as buffer:

        shutil.copyfileobj(
            file.file,
            buffer,
        )

    return filepath


# ==========================================================
# CATEGORY NORMALIZATION
# ==========================================================

def _normalize_db_category(
    category: str,
) -> str:

    value = (
        category or ""
    ).lower().strip()

    mapping = {

        # Refund
        "refund": "REFUND",

        # Damaged product
        "damaged product": "DAMAGED_PRODUCT",
        "damaged_product": "DAMAGED_PRODUCT",
        "damage": "DAMAGED_PRODUCT",

        # Replacement
        #
        # Database does not have REPLACEMENT.
        # Store it as DAMAGED_PRODUCT.
        # ResolutionAgent can still return
        # issue_replacement.
        "replacement": "DAMAGED_PRODUCT",
        "replace": "DAMAGED_PRODUCT",

        # Delivery
        "delivery": "DELIVERY_ISSUE",
        "delivery issue": "DELIVERY_ISSUE",
        "delivery_issue": "DELIVERY_ISSUE",
        "delivery delay": "DELIVERY_ISSUE",
        "delivery_delay": "DELIVERY_ISSUE",

        # Warranty
        "warranty": "WARRANTY",
        "warranty claim": "WARRANTY",
        "warranty_claim": "WARRANTY",

        # Billing
        "billing": "BILLING",
        "billing issue": "BILLING",
        "billing_issue": "BILLING",

        # Service
        "service quality": "SERVICE_QUALITY",
        "service_quality": "SERVICE_QUALITY",

        # Other
        "other": "OTHER",
        "general inquiry": "OTHER",
        "general_inquiry": "OTHER",
    }

    return mapping.get(
        value,
        "OTHER",
    )


# ==========================================================
# CREATE COMPLAINT
# ==========================================================

@router.post(
    "/",
    response_model=ComplaintOut,
    status_code=status.HTTP_201_CREATED,
)
def create_complaint(
    payload: ComplaintCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):

    db_category = _normalize_db_category(
        payload.category
    )

    complaint = Complaint(
        customer_id=current_user.id,

        # IMPORTANT:
        # reference_code is NOT NULL in database.
        reference_code=(
            f"CMP-"
            f"{uuid.uuid4().hex[:8].upper()}"
        ),

        title=payload.title,
        description=payload.description,
        category=db_category,
    )

    db.add(complaint)

    db.flush()

    _log(
        db,
        complaint.id,
        current_user.id,
        "complaint_created",
    )

    db.commit()

    db.refresh(complaint)

    return complaint


# ==========================================================
# LIST COMPLAINTS
# ==========================================================

@router.get(
    "/",
    response_model=PaginatedComplaints,
)
def list_complaints(
    status_filter: Optional[ComplaintStatus] = Query(
        None,
        alias="status",
    ),
    category: Optional[str] = None,
    page: int = Query(
        1,
        ge=1,
    ),
    page_size: int = Query(
        20,
        ge=1,
        le=100,
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):

    query = db.query(Complaint)

    # Customers only see their complaints.
    if current_user.role == UserRole.CUSTOMER:

        query = query.filter(
            Complaint.customer_id
            == current_user.id
        )

    if status_filter:

        query = query.filter(
            Complaint.status
            == status_filter
        )

    if category:

        db_category = _normalize_db_category(
            category
        )

        query = query.filter(
            Complaint.category
            == db_category
        )

    total = query.count()

    items = (
        query
        .order_by(
            Complaint.created_at.desc()
        )
        .offset(
            (page - 1) * page_size
        )
        .limit(page_size)
        .all()
    )

    return PaginatedComplaints(
        total=total,
        page=page,
        page_size=page_size,
        items=items,
    )


# ==========================================================
# GET ONE COMPLAINT
# ==========================================================

@router.get(
    "/{complaint_id}",
    response_model=ComplaintOut,
)
def get_complaint(
    complaint_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):

    complaint = (
        db.query(Complaint)
        .filter(
            Complaint.id
            == complaint_id
        )
        .first()
    )

    if not complaint:

        raise HTTPException(
            status_code=404,
            detail="Complaint not found",
        )

    if (
        current_user.role
        == UserRole.CUSTOMER
        and complaint.customer_id
        != current_user.id
    ):

        raise HTTPException(
            status_code=403,
            detail=(
                "Not authorized to "
                "view this complaint"
            ),
        )

    return complaint


# ==========================================================
# UPDATE COMPLAINT
# ==========================================================

@router.put(
    "/{complaint_id}",
    response_model=ComplaintOut,
)
def update_complaint(
    complaint_id: str,
    payload: ComplaintUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            UserRole.AGENT,
            UserRole.ADMIN,
        )
    ),
):

    complaint = (
        db.query(Complaint)
        .filter(
            Complaint.id
            == complaint_id
        )
        .first()
    )

    if not complaint:

        raise HTTPException(
            status_code=404,
            detail="Complaint not found",
        )

    update_data = payload.model_dump(
        exclude_unset=True
    )

    for field, value in update_data.items():

        setattr(
            complaint,
            field,
            value,
        )

    if (
        payload.status
        == ComplaintStatus.RESOLVED
    ):

        complaint.resolved_at = (
            datetime.utcnow()
        )

    complaint.updated_at = (
        datetime.utcnow()
    )

    _log(
        db,
        complaint.id,
        current_user.id,
        "complaint_updated",
        str(update_data),
    )

    db.commit()

    db.refresh(complaint)

    return complaint


# ==========================================================
# DELETE COMPLAINT
# ==========================================================

@router.delete(
    "/{complaint_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_complaint(
    complaint_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            UserRole.ADMIN
        )
    ),
):

    complaint = (
        db.query(Complaint)
        .filter(
            Complaint.id
            == complaint_id
        )
        .first()
    )

    if not complaint:

        raise HTTPException(
            status_code=404,
            detail="Complaint not found",
        )

    db.delete(complaint)

    db.commit()

    return None


# ==========================================================
# ASSIGN COMPLAINT
# ==========================================================

@router.post(
    "/{complaint_id}/assign",
    response_model=ComplaintOut,
)
def assign_complaint(
    complaint_id: str,
    agent_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            UserRole.ADMIN
        )
    ),
):

    complaint = (
        db.query(Complaint)
        .filter(
            Complaint.id
            == complaint_id
        )
        .first()
    )

    if not complaint:

        raise HTTPException(
            status_code=404,
            detail="Complaint not found",
        )

    agent = (
        db.query(User)
        .filter(
            User.id == agent_id,
            User.role == UserRole.AGENT,
        )
        .first()
    )

    if not agent:

        raise HTTPException(
            status_code=404,
            detail="Agent not found",
        )

    complaint.assigned_agent_id = (
        agent.id
    )

    _log(
        db,
        complaint.id,
        current_user.id,
        "complaint_assigned",
        f"agent={agent.id}",
    )

    db.commit()

    db.refresh(complaint)

    return complaint


# ==========================================================
# UPLOAD EVIDENCE
# ==========================================================

@router.post(
    "/{complaint_id}/evidence",
    response_model=EvidenceOut,
    status_code=status.HTTP_201_CREATED,
)
def upload_evidence(
    complaint_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):

    complaint = (
        db.query(Complaint)
        .filter(
            Complaint.id
            == complaint_id
        )
        .first()
    )

    if not complaint:

        raise HTTPException(
            status_code=404,
            detail="Complaint not found",
        )

    if (
        current_user.role
        == UserRole.CUSTOMER
        and complaint.customer_id
        != current_user.id
    ):

        raise HTTPException(
            status_code=403,
            detail=(
                "Not authorized to "
                "modify this complaint"
            ),
        )

    dest_path = _save_upload(
        complaint.id,
        file,
    )

    evidence = Evidence(
        complaint_id=complaint.id,
        file_path=dest_path,
        file_name=(
            file.filename
            or os.path.basename(
                dest_path
            )
        ),
        evidence_type=_classify_file(
            file.filename
        ),
    )

    db.add(evidence)

    _log(
        db,
        complaint.id,
        current_user.id,
        "evidence_uploaded",
        os.path.basename(
            dest_path
        ),
    )

    db.commit()

    db.refresh(evidence)

    return evidence


# ==========================================================
# HISTORY
# ==========================================================

@router.get(
    "/{complaint_id}/history",
    response_model=list[AuditLogOut],
)
def get_complaint_history(
    complaint_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):

    complaint = (
        db.query(Complaint)
        .filter(
            Complaint.id
            == complaint_id
        )
        .first()
    )

    if not complaint:

        raise HTTPException(
            status_code=404,
            detail="Complaint not found",
        )

    if (
        current_user.role
        == UserRole.CUSTOMER
        and complaint.customer_id
        != current_user.id
    ):

        raise HTTPException(
            status_code=403,
            detail=(
                "Not authorized to "
                "view this complaint"
            ),
        )

    return (
        db.query(AuditLog)
        .filter(
            AuditLog.complaint_id
            == complaint_id
        )
        .order_by(
            AuditLog.created_at.desc()
        )
        .all()
    )


# ==========================================================
# ONE-SHOT COMPLAINT SUBMISSION
# ==========================================================

@router.post(
    "/submit",
    status_code=status.HTTP_201_CREATED,
)
async def submit_complaint(
    title: str = Form(...),
    description: str = Form(...),
    category: str = Form(...),

    # IMPORTANT:
    # This accepts actual uploaded files.
    files: List[UploadFile] = File(...),

    db: Session = Depends(get_db),

    current_user: User = Depends(
        get_current_user
    ),
):

    """
    One-shot complaint submission.

    Receives:

    - title
    - description
    - category
    - uploaded evidence files

    Then:

    1. Creates complaint
    2. Saves evidence
    3. Runs AI pipeline
    4. Saves fraud assessment
    5. Saves resolution
    6. Saves workflow state
    7. Saves agent execution logs
    """

    # ======================================================
    # 1. CATEGORY
    # ======================================================

    original_category = (
        category or ""
    ).lower().strip()

    db_category = _normalize_db_category(
        original_category
    )

    # ======================================================
    # 2. CREATE COMPLAINT
    # ======================================================

    complaint = Complaint(
        customer_id=current_user.id,

        # THIS FIXES YOUR CURRENT ERROR
        reference_code=(
            f"CMP-"
            f"{uuid.uuid4().hex[:8].upper()}"
        ),

        title=title,
        description=description,
        category=db_category,
    )

    db.add(complaint)

    db.flush()

    _log(
        db,
        complaint.id,
        current_user.id,
        "complaint_created",
    )

    # ======================================================
    # 3. SAVE FILES
    # ======================================================

    paths: List[str] = []

    for file in files:

        if (
            file is None
            or not file.filename
        ):
            continue

        filepath = _save_upload(
            complaint.id,
            file,
        )

        paths.append(filepath)

        evidence = Evidence(
            complaint_id=complaint.id,
            file_path=filepath,
            file_name=file.filename,
            evidence_type=_classify_file(
                file.filename
            ),
        )

        db.add(evidence)

    if paths:

        _log(
            db,
            complaint.id,
            current_user.id,
            "evidence_uploaded",
            f"{len(paths)} file(s)",
        )

    db.flush()

    # ======================================================
    # 4. RUN AI
    # ======================================================

    orchestrator = Orchestrator()

    context = orchestrator.handle_complaint(
        complaint_id=str(
            complaint.id
        ),
        customer_id=str(
            current_user.id
        ),
        raw_text=description,
        channel="web",

        # Send original category to AI.
        #
        # Example:
        # "replacement" remains "replacement"
        # for ResolutionAgent.
        attachments=paths,
    )

    print(
        orchestrator.explain(
            context
        )
    )

    # ======================================================
    # 5. AI RESULTS
    # ======================================================

    if context.priority:

        try:

            complaint.priority = (
                ComplaintPriority(
                    context.priority
                )
            )

        except (
            ValueError,
            TypeError,
        ):

            print(
                "Warning: Invalid priority "
                f"from AI: "
                f"{context.priority}"
            )

    if (
        context.fraud_score
        is not None
    ):

        complaint.fraud_risk_score = (
            context.fraud_score
        )

    if context.sentiment:

        complaint.sentiment_score = 0.5

    complaint.updated_at = (
        datetime.utcnow()
    )

    # ======================================================
    # 6. WORKFLOW STATUS
    # ======================================================

    if context.escalated:

        complaint.status = (
            ComplaintStatus.ESCALATED
        )

    elif context.resolution:

        complaint.status = (
            ComplaintStatus.RESOLVED
        )

        complaint.is_auto_resolved = True

        complaint.resolved_at = (
            datetime.utcnow()
        )

    else:

        complaint.status = (
            ComplaintStatus.UNDER_REVIEW
        )

    # ======================================================
    # 7. FRAUD ASSESSMENT
    # ======================================================

    if (
        context.fraud_score
        is not None
    ):

        if context.fraud_score > 0.8:

            risk_level = "high"

        elif context.fraud_score > 0.4:

            risk_level = "medium"

        else:

            risk_level = "low"

        db.add(
            FraudAssessment(
                complaint_id=complaint.id,
                risk_score=context.fraud_score,
                risk_level=risk_level,
                anomaly_flags=(
                    context.fraud_flags
                    or []
                ),
                behavioral_flags=[],
                is_flagged_for_manual_review=(
                    context.escalated
                ),
            )
        )

    # ======================================================
    # 8. RESOLUTION
    # ======================================================

    if context.resolution:

        try:

            policy_citations = (
                dict(
                    context.policy_findings
                )
                if context.policy_findings
                else None
            )

        except (
            TypeError,
            ValueError,
        ):

            policy_citations = {
                "raw": [
                    str(item)
                    for item in (
                        context.policy_findings
                        or []
                    )
                ]
            }

        resolution_data = (
            context.resolution
        )

        decision = (
            resolution_data.get(
                "decision",
                "manual_review",
            )
        )

        amount = (
            resolution_data.get(
                "amount"
            )
        )

        justification = (
            resolution_data.get(
                "justification",
                resolution_data.get(
                    "reason",
                    "Generated by AI",
                ),
            )
        )

        db.add(
            Resolution(
                complaint_id=complaint.id,
                decision=decision,
                resolution_amount=amount,
                justification=justification,
                policy_citations=(
                    policy_citations
                ),
                requires_human_approval=(
                    context.escalated
                ),
            )
        )

    # ======================================================
    # 9. WORKFLOW STATE
    # ======================================================

    db.add(
        WorkflowState(
            complaint_id=complaint.id,
            current_node=(
                context.workflow_state
            ),
            graph_state={
                "intent": context.intent,
                "category": context.category,
                "priority": context.priority,
                "workflow": (
                    context.workflow_state
                ),
            },
        )
    )

    # ======================================================
    # 10. AGENT EXECUTION LOGS
    # ======================================================

    for trace in (
        context.agent_trace
    ):

        try:

            agent_name = AgentName(
                trace["agent_name"]
            )

            db.add(
                AgentExecutionLog(
                    complaint_id=complaint.id,
                    agent_name=agent_name,
                    reasoning=trace.get(
                        "reasoning",
                        "",
                    ),
                    confidence=trace.get(
                        "confidence",
                        0.0,
                    ),
                    output_summary=str(
                        trace.get(
                            "data",
                            {},
                        )
                    ),
                    latency_ms=int(
                        trace.get(
                            "duration_ms",
                            0,
                        )
                    ),
                    status=(
                        "success"
                        if trace.get(
                            "success",
                            False,
                        )
                        else "failed"
                    ),
                )
            )

        except (
            ValueError,
            TypeError,
        ) as exc:

            print(
                "Agent log warning: "
                f"{exc}"
            )

    # ======================================================
    # 11. FINAL AUDIT
    # ======================================================

    _log(
        db,
        complaint.id,
        current_user.id,
        "complaint_ai_processed",
        context.workflow_state,
    )

    # ======================================================
    # 12. COMMIT
    # ======================================================

    db.commit()

    # DO NOT db.refresh(complaint) HERE.
    #
    # We return the AI result directly.
    # This avoids the enum deserialization problem
    # you previously encountered.

    return {
        "complaint_id": str(
            complaint.id
        ),

        "reference_code": (
            complaint.reference_code
        ),

        "workflow": (
            context.workflow_state
        ),

        "category": (
            context.category
        ),

        "fraud_score": (
            context.fraud_score
        ),

        "fraud_flags": (
            context.fraud_flags
        ),

        "resolution": (
            context.resolution
        ),

        "escalated": (
            context.escalated
        ),

        "reason": (
            context.escalation_reason
        ),

        "trace": (
            context.agent_trace
        ),
    }