# Integration Notes — backend/database/

## Drop-in placement
Copy this whole `backend/` folder (or just `database/`) into your repo at
`RESOLVIX-AI/backend/database/`. It assumes your project root is on
`PYTHONPATH` so `from backend.database.connection import ...` resolves —
that's already true if you run FastAPI from the repo root (`uvicorn backend.main:app`).

## Requirements to add to requirements.txt
```
sqlalchemy>=2.0
psycopg2-binary>=2.9
asyncpg>=0.29        # optional, only if you use get_async_db()
alembic>=1.13
pydantic>=2.6
python-dotenv>=1.0
```

## .env keys this expects
```
POSTGRES_USER=resolvix_user
POSTGRES_PASSWORD=resolvix_pass
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=resolvix_ai
DATABASE_URL=postgresql+psycopg2://resolvix_user:resolvix_pass@localhost:5432/resolvix_ai
SQL_ECHO=false
```

## Wiring into backend/main.py
```python
from fastapi import FastAPI
from backend.database.connection import engine, Base
from backend.database import models  # registers tables on Base.metadata

app = FastAPI(title="RESOLVIX-AI")

# Dev only — in staging/prod, run `alembic upgrade head` instead
# Base.metadata.create_all(bind=engine)
```

## Wiring into backend/api/complaints.py
```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.database.connection import get_db
from backend.database import models, schema

router = APIRouter(prefix="/complaints", tags=["complaints"])

@router.post("/", response_model=schema.ComplaintOut)
def create_complaint(payload: schema.ComplaintCreate, db: Session = Depends(get_db)):
    complaint = models.Complaint(
        customer_id=current_user_id,      # from your auth dependency
        reference_code=generate_reference_code(),
        **payload.model_dump(),
    )
    db.add(complaint)
    db.flush()
    return complaint
```

## Wiring into ai/agents/orchestrator.py (background/async context)
```python
from backend.database.connection import db_session
from backend.database import models

def run_agent_pipeline(complaint_id: str):
    with db_session() as db:
        complaint = db.query(models.Complaint).get(complaint_id)
        # ... run agents, then:
        db.add(models.AgentExecutionLog(
            complaint_id=complaint_id,
            agent_name=models.AgentName.FRAUD_AGENT,
            reasoning="...",
            confidence=0.92,
        ))
```

## Running migrations
```bash
cd RESOLVIX-AI
alembic -c backend/database/migrations/alembic.ini upgrade head
```

## Notes
- `models.py` is the single source of truth for table structure — `schema.py`
  Pydantic models intentionally mirror it but stay decoupled so the API
  contract doesn't break if you refactor a column.
- `AgentExecutionLog` is what feeds `ai/explainable_ai/audit_summary.py` and
  the "Explainability" slide/feature — every agent should write one row per
  decision it makes.
- `FraudAssessment` and `Resolution` are 1:1 with `Complaint` (unique FK) —
  one verdict per complaint, re-runs should update the existing row, not insert a new one.
- Swap `postgresql+psycopg2` for `sqlite:///./resolvix.db` in `DATABASE_URL`
  for fast local hackathon demos with zero setup.
