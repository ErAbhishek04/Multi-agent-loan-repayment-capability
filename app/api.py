from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import chromadb
import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://app:app@localhost:5432/agentdb")
CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_data")
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(title="Clearline local review API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def ensure_review_columns(conn: psycopg.Connection[Any]) -> None:
    conn.execute("ALTER TABLE loan_applications ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ")
    conn.execute("ALTER TABLE loan_applications ADD COLUMN IF NOT EXISTS reviewed_by VARCHAR(100)")


def assessment_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    (
        application_id,
        applicant_name,
        monthly_income,
        monthly_debt,
        requested_payment,
        employment_months,
        credit_score,
        reviewed_at,
        reviewed_by,
    ) = row
    income = float(monthly_income)
    debt_to_income = (float(monthly_debt) + float(requested_payment)) / income
    indicators = {
        "debt_to_income_below_40_percent": debt_to_income <= 0.40,
        "credit_score_at_least_650": credit_score >= 650,
        "employment_at_least_12_months": employment_months >= 12,
    }
    passed = sum(indicators.values())
    return {
        "id": application_id,
        "name": applicant_name,
        "income": income,
        "debt": float(monthly_debt),
        "payment": float(requested_payment),
        "employment": employment_months,
        "credit": credit_score,
        "dti": round(debt_to_income, 4),
        "indicators": indicators,
        "passed_signals": passed,
        "status": "reviewed" if reviewed_at else "ready" if passed == 3 else "attention",
        "reviewed_at": reviewed_at.isoformat() if reviewed_at else None,
        "reviewed_by": reviewed_by,
    }


@app.get("/api/health")
def health() -> dict[str, str]:
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            conn.execute("SELECT 1")
        database = "connected"
    except Exception:
        database = "unavailable"
    return {"status": "ok", "database": database}


@app.get("/api/applications")
def list_applications(
    search: str = Query(default="", max_length=100),
    status: str = Query(default="all", pattern="^(all|ready|attention|reviewed)$"),
) -> list[dict[str, Any]]:
    query = """
        SELECT id, applicant_name, monthly_income, monthly_debt,
               requested_payment, employment_months, credit_score,
               reviewed_at, reviewed_by
        FROM loan_applications
        WHERE (%s = '' OR applicant_name ILIKE %s OR CAST(id AS TEXT) = %s)
        ORDER BY id
    """
    search_term = f"%{search}%"
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            ensure_review_columns(conn)
            rows = conn.execute(query, (search, search_term, search)).fetchall()
            conn.commit()
    except psycopg.OperationalError as error:
        raise HTTPException(status_code=503, detail="PostgreSQL is unavailable or credentials are invalid") from error
    applications = [assessment_from_row(row) for row in rows]
    if status != "all":
        applications = [item for item in applications if item["status"] == status]
    return applications


@app.get("/api/applications/{application_id}/assessment")
def get_assessment(application_id: int) -> dict[str, Any]:
    query = """
        SELECT id, applicant_name, monthly_income, monthly_debt,
               requested_payment, employment_months, credit_score,
               reviewed_at, reviewed_by
        FROM loan_applications WHERE id = %s
    """
    with psycopg.connect(DATABASE_URL) as conn:
        ensure_review_columns(conn)
        row = conn.execute(query, (application_id,)).fetchone()
        conn.commit()
    if row is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return assessment_from_row(row)


@app.post("/api/applications/{application_id}/review")
def update_review(application_id: int, reviewed: bool = True, reviewer: str = "Alex Rivera") -> dict[str, Any]:
    reviewed_at = datetime.now(timezone.utc) if reviewed else None
    query = """
        UPDATE loan_applications
        SET reviewed_at = %s, reviewed_by = %s
        WHERE id = %s
        RETURNING id, applicant_name, monthly_income, monthly_debt,
                  requested_payment, employment_months, credit_score,
                  reviewed_at, reviewed_by
    """
    with psycopg.connect(DATABASE_URL) as conn:
        ensure_review_columns(conn)
        row = conn.execute(query, (reviewed_at, reviewer if reviewed else None, application_id)).fetchone()
        conn.commit()
    if row is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return assessment_from_row(row)


@app.get("/api/knowledge/search")
def search_knowledge(q: str = Query(min_length=2, max_length=200), top_k: int = Query(default=3, ge=1, le=10)) -> list[dict[str, Any]]:
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_or_create_collection(name="company_knowledge")
    if collection.count() == 0:
        return []
    result = collection.query(query_texts=[q], n_results=top_k)
    return [
        {"id": doc_id, "document": document, "metadata": metadata}
        for doc_id, document, metadata in zip(
            result.get("ids", [[]])[0],
            result.get("documents", [[]])[0],
            result.get("metadatas", [[]])[0],
        )
    ]


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
