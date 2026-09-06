from __future__ import annotations

import os
import asyncio
import base64
import hashlib
import hmac
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import chromadb
import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi import File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://app:app@localhost:5433/agentdb")
DB_CONNECT_TIMEOUT = int(os.getenv("DB_CONNECT_TIMEOUT", "3"))
LOGIN_USERNAME = os.getenv("LOGIN_USERNAME", "reviewer")
LOGIN_PASSWORD = os.getenv("LOGIN_PASSWORD", "change-me")
SESSION_SECRET = os.getenv("SESSION_SECRET", "local-development-secret-change-me")
SESSION_COOKIE = "clearline_session"
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
    conn.execute("ALTER TABLE loan_applications ADD COLUMN IF NOT EXISTS loan_amount NUMERIC(12, 2) DEFAULT 30000")
    conn.execute("ALTER TABLE loan_applications ADD COLUMN IF NOT EXISTS term_months INTEGER DEFAULT 36")
    conn.execute("""CREATE TABLE IF NOT EXISTS application_documents (
        id SERIAL PRIMARY KEY, application_id INTEGER NOT NULL REFERENCES loan_applications(id) ON DELETE CASCADE,
        file_name VARCHAR(255) NOT NULL, document_type VARCHAR(80) NOT NULL,
        extracted_status VARCHAR(40) NOT NULL DEFAULT 'queued', extracted_income NUMERIC(12, 2),
        uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    conn.execute("""CREATE TABLE IF NOT EXISTS audit_events (
        id SERIAL PRIMARY KEY, application_id INTEGER REFERENCES loan_applications(id) ON DELETE CASCADE,
        event_type VARCHAR(80) NOT NULL, reviewer VARCHAR(100) NOT NULL, note TEXT NOT NULL DEFAULT '',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    conn.execute("""CREATE TABLE IF NOT EXISTS repayment_events (
        id SERIAL PRIMARY KEY, application_id INTEGER NOT NULL REFERENCES loan_applications(id) ON DELETE CASCADE,
        due_date DATE NOT NULL, amount_due NUMERIC(12, 2) NOT NULL, amount_paid NUMERIC(12, 2) NOT NULL DEFAULT 0,
        paid_at TIMESTAMPTZ)""")


class SimulationInput(BaseModel):
    monthly_income: float = Field(gt=0)
    monthly_debt: float = Field(ge=0)
    requested_payment: float = Field(gt=0)


class AuditInput(BaseModel):
    event_type: str = Field(min_length=2, max_length=80)
    reviewer: str = Field(default="Alex Rivera", min_length=2, max_length=100)
    note: str = Field(default="", max_length=1000)


class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


def create_session(username: str) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"sub": username, "exp": int(time.time()) + 8 * 60 * 60}, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def session_username(token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    payload, signature = token.rsplit(".", 1)
    expected = hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        decoded = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        data = json.loads(decoded)
        if int(data["exp"]) < int(time.time()):
            return None
        return str(data["sub"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


@app.middleware("http")
async def protect_api(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.url.path not in {"/api/health", "/api/auth/login"}:
        if session_username(request.cookies.get(SESSION_COOKIE)) is None:
            return Response(content=json.dumps({"detail": "Authentication required"}), status_code=401, media_type="application/json")
    return await call_next(request)


@app.post("/api/auth/login")
def login(payload: LoginInput, response: Response) -> dict[str, str]:
    if not (hmac.compare_digest(payload.username, LOGIN_USERNAME) and hmac.compare_digest(payload.password, LOGIN_PASSWORD)):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    response.set_cookie(SESSION_COOKIE, create_session(payload.username), httponly=True, samesite="lax", max_age=8 * 60 * 60)
    return {"username": payload.username}


@app.post("/api/auth/logout")
def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(SESSION_COOKIE)
    return {"status": "signed_out"}


@app.get("/api/auth/me")
def current_user(request: Request) -> dict[str, str]:
    username = session_username(request.cookies.get(SESSION_COOKIE))
    if username is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {"username": username}


def require_application(conn: psycopg.Connection[Any], application_id: int) -> None:
    if conn.execute("SELECT 1 FROM loan_applications WHERE id = %s", (application_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="Application not found")


def assessment_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    (
        application_id,
        applicant_name,
        monthly_income,
        monthly_debt,
        requested_payment,
        employment_months,
        credit_score,
        loan_amount,
        term_months,
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
        "loan_amount": float(loan_amount),
        "term_months": term_months,
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
        with psycopg.connect(DATABASE_URL, connect_timeout=DB_CONNECT_TIMEOUT) as conn:
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
             loan_amount, term_months,
               reviewed_at, reviewed_by
        FROM loan_applications
        WHERE (%s = '' OR applicant_name ILIKE %s OR CAST(id AS TEXT) = %s)
        ORDER BY id
    """
    search_term = f"%{search}%"
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=DB_CONNECT_TIMEOUT) as conn:
            ensure_review_columns(conn)
            rows = conn.execute(query, (search, search_term, search)).fetchall()
            conn.commit()
    except psycopg.OperationalError as error:
        raise HTTPException(status_code=503, detail="PostgreSQL is unavailable or credentials are invalid") from error
    applications = [assessment_from_row(row) for row in rows]
    if status != "all":
        applications = [item for item in applications if item["status"] == status]
    return applications


@app.get("/api/analytics/summary")
def analytics_summary() -> dict[str, Any]:
    query = """
        SELECT COUNT(*) FILTER (WHERE reviewed_at IS NULL),
               COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY
                   (monthly_debt + requested_payment) / monthly_income), 0),
               COALESCE(COUNT(DISTINCT d.application_id)::float / NULLIF(COUNT(l.id), 0), 0)
        FROM loan_applications l
        LEFT JOIN application_documents d ON d.application_id = l.id
    """
    with psycopg.connect(DATABASE_URL, connect_timeout=DB_CONNECT_TIMEOUT) as conn:
        ensure_review_columns(conn)
        row = conn.execute(query).fetchone()
        conn.commit()
    return {
        "needs_review": int(row[0]),
        "median_dti": round(float(row[1]), 4),
        "evidence_coverage": round(float(row[2]), 4),
    }


@app.get("/api/applications/{application_id}/assessment")
def get_assessment(application_id: int) -> dict[str, Any]:
    query = """
        SELECT id, applicant_name, monthly_income, monthly_debt,
             requested_payment, employment_months, credit_score,
             loan_amount, term_months,
               reviewed_at, reviewed_by
        FROM loan_applications WHERE id = %s
    """
    with psycopg.connect(DATABASE_URL, connect_timeout=DB_CONNECT_TIMEOUT) as conn:
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
              loan_amount, term_months,
                  reviewed_at, reviewed_by
    """
    with psycopg.connect(DATABASE_URL, connect_timeout=DB_CONNECT_TIMEOUT) as conn:
        ensure_review_columns(conn)
        require_application(conn, application_id)
        row = conn.execute(query, (reviewed_at, reviewer if reviewed else None, application_id)).fetchone()
        conn.execute(
            "INSERT INTO audit_events (application_id, event_type, reviewer, note) VALUES (%s, %s, %s, %s)",
            (application_id, "review_reopened" if not reviewed else "review_marked", reviewer, "Review state changed"),
        )
        conn.commit()
    if row is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return assessment_from_row(row)


@app.post("/api/applications/{application_id}/simulate")
def simulate_application(application_id: int, payload: SimulationInput) -> dict[str, Any]:
    """Run a what-if affordability calculation without changing stored application data."""
    with psycopg.connect(DATABASE_URL, connect_timeout=DB_CONNECT_TIMEOUT) as conn:
        ensure_review_columns(conn)
        row = conn.execute(
            "SELECT credit_score, employment_months FROM loan_applications WHERE id = %s",
            (application_id,),
        ).fetchone()
        conn.commit()
    if row is None:
        raise HTTPException(status_code=404, detail="Application not found")
    ratio = (payload.monthly_debt + payload.requested_payment) / payload.monthly_income
    return {
        "application_id": application_id,
        "monthly_income": payload.monthly_income,
        "monthly_debt": payload.monthly_debt,
        "requested_payment": payload.requested_payment,
        "debt_to_income_ratio": round(ratio, 4),
        "indicators": {
            "debt_to_income_below_40_percent": ratio <= 0.40,
            "credit_score_at_least_650": row[0] >= 650,
            "employment_at_least_12_months": row[1] >= 12,
        },
        "persisted": False,
    }


@app.get("/api/applications/{application_id}/debate")
def specialist_debate(application_id: int) -> dict[str, Any]:
    assessment = get_assessment(application_id)
    dti_pass = assessment["indicators"]["debt_to_income_below_40_percent"]
    credit_pass = assessment["indicators"]["credit_score_at_least_650"]
    employment_pass = assessment["indicators"]["employment_at_least_12_months"]
    return {
        "application_id": application_id,
        "decision_support_only": True,
        "specialists": [
            {"name": "Affordability specialist", "position": "pass" if dti_pass else "attention", "reason": f"DTI is {assessment['dti']:.1%}."},
            {"name": "Credit specialist", "position": "pass" if credit_pass else "attention", "reason": f"Credit score is {assessment['credit']}."},
            {"name": "Stability specialist", "position": "pass" if employment_pass else "attention", "reason": f"Employment history is {assessment['employment']} months."},
        ],
    }


@app.post("/api/applications/{application_id}/ai-review")
async def ai_review(application_id: int) -> dict[str, Any]:
    """Generate a grounded AI explanation from verified application facts."""
    try:
        assessment = get_assessment(application_id)
        facts = json.dumps({
            "applicant": assessment["name"],
            "monthly_income": assessment["income"],
            "monthly_debt": assessment["debt"],
            "requested_payment": assessment["payment"],
            "debt_to_income_ratio": assessment["dti"],
            "credit_score": assessment["credit"],
            "employment_months": assessment["employment"],
            "indicators": assessment["indicators"],
        })
        request_body = json.dumps({
            "model": os.getenv("LLM_MODEL", "llama3.2"),
            "temperature": 0.1,
            "max_tokens": 350,
            "messages": [
                {"role": "system", "content": "You are a loan review explanation assistant. Use only the supplied verified facts. Explain the debt-to-income ratio and each indicator in plain language. Recommend human verification steps. Never approve, reject, predict creditworthiness, or invent facts. State that this is decision support only."},
                {"role": "user", "content": f"Explain this application for a qualified reviewer:\n{facts}"},
            ],
        }).encode()
        model_base_url = os.getenv("LLM_BASE_URL", "http://127.0.0.1:11434/v1").replace("://localhost:", "://127.0.0.1:")
        model_url = f"{model_base_url.rstrip('/')}/chat/completions"

        def request_model() -> str:
            model_request = urllib.request.Request(
                model_url,
                data=request_body,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {os.getenv('LLM_API_KEY', 'ollama')}"},
            )
            with urllib.request.urlopen(model_request, timeout=30) as model_response:
                response_data = json.loads(model_response.read().decode())
            return response_data.get("choices", [{}])[0].get("message", {}).get("content", "")

        answer = await asyncio.wait_for(asyncio.to_thread(request_model), timeout=8)
        if not answer:
            answer = "The AI model returned no explanation."
        return {"application_id": application_id, "answer": answer, "decision_support_only": True, "model": os.getenv("LLM_MODEL", "llama3.2"), "source": "PostgreSQL assessment + local model"}
    except asyncio.TimeoutError as error:
        raise HTTPException(status_code=503, detail="Ollama is reachable but text generation is stalled. Restart Ollama and retry the AI reviewer.") from error
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"AI review unavailable: {error}") from error


@app.post("/api/applications/{application_id}/documents")
def upload_document(application_id: int, document: UploadFile = File(...)) -> dict[str, Any]:
    if not document.filename:
        raise HTTPException(status_code=400, detail="A document filename is required")
    document_type = document.filename.rsplit(".", 1)[-1].lower() if "." in document.filename else "unknown"
    allowed_types = {"pdf", "png", "jpg", "jpeg", "csv"}
    if document_type not in allowed_types:
        raise HTTPException(status_code=415, detail="Only PDF, PNG, JPG, JPEG, and CSV files are supported")
    content = document.file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Documents must be 10 MB or smaller")
    with psycopg.connect(DATABASE_URL, connect_timeout=DB_CONNECT_TIMEOUT) as conn:
        ensure_review_columns(conn)
        require_application(conn, application_id)
        row = conn.execute(
            """INSERT INTO application_documents (application_id, file_name, document_type)
               VALUES (%s, %s, %s) RETURNING id, uploaded_at""",
            (application_id, document.filename, document_type),
        ).fetchone()
        conn.execute(
            "INSERT INTO audit_events (application_id, event_type, reviewer, note) VALUES (%s, %s, %s, %s)",
            (application_id, "document_uploaded", "Alex Rivera", document.filename),
        )
        conn.commit()
    return {"id": row[0], "application_id": application_id, "file_name": document.filename, "document_type": document_type, "extraction": "queued", "uploaded_at": row[1].isoformat()}


@app.get("/api/applications/{application_id}/documents")
def list_documents(application_id: int) -> list[dict[str, Any]]:
    with psycopg.connect(DATABASE_URL, connect_timeout=DB_CONNECT_TIMEOUT) as conn:
        ensure_review_columns(conn)
        rows = conn.execute("SELECT id, file_name, document_type, extracted_status, uploaded_at FROM application_documents WHERE application_id = %s ORDER BY uploaded_at DESC", (application_id,)).fetchall()
        conn.commit()
    return [{"id": row[0], "file_name": row[1], "document_type": row[2], "status": row[3], "uploaded_at": row[4].isoformat()} for row in rows]


@app.post("/api/applications/{application_id}/audit")
def create_audit_event(application_id: int, payload: AuditInput) -> dict[str, Any]:
    with psycopg.connect(DATABASE_URL, connect_timeout=DB_CONNECT_TIMEOUT) as conn:
        ensure_review_columns(conn)
        require_application(conn, application_id)
        row = conn.execute("INSERT INTO audit_events (application_id, event_type, reviewer, note) VALUES (%s, %s, %s, %s) RETURNING id, created_at", (application_id, payload.event_type, payload.reviewer, payload.note)).fetchone()
        conn.commit()
    return {"id": row[0], "application_id": application_id, "event_type": payload.event_type, "reviewer": payload.reviewer, "note": payload.note, "created_at": row[1].isoformat()}


@app.get("/api/applications/{application_id}/audit")
def list_audit_events(application_id: int) -> list[dict[str, Any]]:
    with psycopg.connect(DATABASE_URL, connect_timeout=DB_CONNECT_TIMEOUT) as conn:
        ensure_review_columns(conn)
        rows = conn.execute("SELECT id, event_type, reviewer, note, created_at FROM audit_events WHERE application_id = %s ORDER BY created_at DESC", (application_id,)).fetchall()
        conn.commit()
    return [{"id": row[0], "event_type": row[1], "reviewer": row[2], "note": row[3], "created_at": row[4].isoformat()} for row in rows]


@app.get("/api/monitoring/repayments")
def repayment_monitoring() -> list[dict[str, Any]]:
    with psycopg.connect(DATABASE_URL, connect_timeout=DB_CONNECT_TIMEOUT) as conn:
        ensure_review_columns(conn)
        rows = conn.execute("""SELECT l.id, l.applicant_name, COALESCE(SUM(r.amount_due), 0),
            COALESCE(SUM(r.amount_paid), 0), COUNT(r.id) FROM loan_applications l
            LEFT JOIN repayment_events r ON r.application_id = l.id GROUP BY l.id ORDER BY l.id""").fetchall()
        conn.commit()
    return [{"application_id": row[0], "applicant_name": row[1], "amount_due": float(row[2]), "amount_paid": float(row[3]), "events": row[4], "health": "on_track" if row[2] and row[3] / row[2] >= 0.5 else "watch"} for row in rows]


@app.get("/api/analytics/fairness")
def fairness_summary() -> dict[str, Any]:
    with psycopg.connect(DATABASE_URL, connect_timeout=DB_CONNECT_TIMEOUT) as conn:
        ensure_review_columns(conn)
        rows = conn.execute("SELECT CASE WHEN credit_score >= 650 THEN 'credit_650_plus' ELSE 'credit_below_650' END, COUNT(*), AVG(CASE WHEN reviewed_at IS NOT NULL THEN 1 ELSE 0 END) FROM loan_applications GROUP BY 1 ORDER BY 1").fetchall()
        conn.commit()
    return {"method": "synthetic operational cohorts, not protected attributes", "groups": [{"cohort": row[0], "applications": row[1], "reviewed_rate": float(row[2])} for row in rows], "warning": "For monitoring and fairness testing only; never use protected characteristics to automate lending decisions."}


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
