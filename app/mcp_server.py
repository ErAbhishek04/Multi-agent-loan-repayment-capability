from __future__ import annotations

import os
from typing import Any

import chromadb
import psycopg
from dotenv import load_dotenv
from mcp.server import MCPServer

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://app:app@localhost:5432/agentdb",
)
CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_data")

mcp = MCPServer("employee-data-server")


def _chroma_collection():
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    return client.get_or_create_collection(name="company_knowledge")


@mcp.tool()
def search_employees(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Search employees in PostgreSQL by name, department, role, or skill keywords."""
    limit = max(1, min(limit, 20))
    like = f"%{query}%"
    sql = """
        SELECT id, name, department, role, salary, skills
        FROM employees
        WHERE name ILIKE %s
           OR department ILIKE %s
           OR role ILIKE %s
           OR skills ILIKE %s
        ORDER BY id
        LIMIT %s
    """
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(sql, (like, like, like, like, limit)).fetchall()
        columns = ["id", "name", "department", "role", "salary", "skills"]
        return [dict(zip(columns, row)) for row in rows]


@mcp.tool()
def get_department_stats(department: str) -> dict[str, Any]:
    """Return employee count and salary statistics for a department from PostgreSQL."""
    sql = """
        SELECT COUNT(*) AS employee_count,
               COALESCE(AVG(salary), 0) AS average_salary,
               COALESCE(MIN(salary), 0) AS min_salary,
               COALESCE(MAX(salary), 0) AS max_salary
        FROM employees
        WHERE department ILIKE %s
    """
    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute(sql, (department,)).fetchone()
    return {
        "department": department,
        "employee_count": int(row[0]),
        "average_salary": float(row[1]),
        "min_salary": int(row[2]),
        "max_salary": int(row[3]),
    }


@mcp.tool()
def assess_loan_application(application_id: int) -> dict[str, Any]:
    """Calculate transparent loan affordability indicators for human-reviewed decision support.

    This tool does not make an approval or rejection decision. It returns the source
    values, ratios, indicator results, and a recommendation for a qualified reviewer.
    """
    sql = """
        SELECT id, applicant_name, monthly_income, monthly_debt,
               requested_payment, employment_months, credit_score
        FROM loan_applications
        WHERE id = %s
    """
    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute(sql, (application_id,)).fetchone()

    if row is None:
        return {"status": "not_found", "application_id": application_id}

    (
        record_id,
        applicant_name,
        monthly_income,
        monthly_debt,
        requested_payment,
        employment_months,
        credit_score,
    ) = row
    income = float(monthly_income)
    debt = float(monthly_debt)
    payment = float(requested_payment)
    debt_to_income = (debt + payment) / income

    indicators = {
        "debt_to_income_below_40_percent": debt_to_income <= 0.40,
        "credit_score_at_least_650": credit_score >= 650,
        "employment_at_least_12_months": employment_months >= 12,
    }
    passed = sum(indicators.values())
    recommendation = (
        "eligible_for_human_review"
        if passed == len(indicators)
        else "needs_additional_review"
    )

    return {
        "status": "ok",
        "application_id": record_id,
        "applicant_name": applicant_name,
        "inputs": {
            "monthly_income": income,
            "monthly_debt": debt,
            "requested_payment": payment,
            "employment_months": employment_months,
            "credit_score": credit_score,
        },
        "metrics": {"debt_to_income_ratio": round(debt_to_income, 4)},
        "indicators": indicators,
        "recommendation": recommendation,
        "review_note": "This is decision support, not an automated lending decision.",
    }


@mcp.tool()
def add_knowledge(doc_id: str, document: str, source: str = "manual") -> dict[str, str]:
    """Add a knowledge document to Chroma for semantic retrieval."""
    collection = _chroma_collection()
    collection.upsert(
        ids=[doc_id],
        documents=[document],
        metadatas=[{"source": source}],
    )
    return {"status": "ok", "id": doc_id, "source": source}


@mcp.tool()
def semantic_search(query: str, top_k: int = 3) -> list[dict[str, Any]]:
    """Search company knowledge in Chroma using semantic similarity."""
    top_k = max(1, min(top_k, 10))
    collection = _chroma_collection()
    if collection.count() == 0:
        return []

    result = collection.query(query_texts=[query], n_results=top_k)
    ids = result.get("ids", [[]])[0]
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]

    return [
        {
            "id": ids[i],
            "document": documents[i],
            "metadata": metadatas[i],
            "distance": distances[i] if i < len(distances) else None,
        }
        for i in range(len(ids))
    ]


if __name__ == "__main__":
    mcp.run()
