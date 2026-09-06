# Simple MCP + Multi-Agent + PostgreSQL + Chroma

A small learning project showing this flow:

User -> Manager Agent -> Specialist Agents -> MCP Server -> PostgreSQL / Chroma

The project uses the current MCP Python SDK v2 line and the OpenAI Agents SDK with a local OpenAI-compatible model endpoint. The MCP server is local and uses stdio, so the agent process launches it as a child process.

## Components

- **Manager agent**: owns the final answer and delegates work.
- **SQL Specialist**: uses MCP tools backed by PostgreSQL.
- **Knowledge Specialist**: uses MCP tools backed by Chroma.
- **Loan Risk Specialist**: calculates explainable affordability indicators from loan applications.
- **Review workspace**: includes what-if simulation, specialist perspectives, document intake, repayment monitoring, fairness testing, and an auditable review workflow.
- **MCP server**: exposes five tools:
  - `search_employees`
  - `get_department_stats`
       - `assess_loan_application`
  - `add_knowledge`
  - `semantic_search`
- **PostgreSQL**: employee records.
- **Chroma**: persistent local semantic knowledge base.

## 1. Prerequisites

- Python 3.10+
- Docker Desktop
- Ollama (or another local OpenAI-compatible model server)

The MCP Python SDK currently documents Python 3.10+ and MCP v2 as the current stable release line.

## 2. Create environment

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

The default configuration uses Ollama with the `llama3.2` model. Install Ollama, then download the model:

```powershell
ollama pull llama3.2
```

To use another local server or model, set `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL` in `.env`. Tracing export is disabled, so an `OPENAI_API_KEY` is not required.

The dashboard uses a local reviewer login. Set `LOGIN_USERNAME`, `LOGIN_PASSWORD`, and a long random `SESSION_SECRET` in `.env`. The example defaults are `reviewer` and `change-me`; replace them before sharing the app.

## 3. Start PostgreSQL

```powershell
docker compose up -d postgres
```

The database is seeded automatically on the first startup.

## 4. Seed Chroma

```powershell
python app/seed_knowledge.py
```

If PostgreSQL was already started before the loan schema was added, recreate the local database volume once so the initialization script runs again:

```powershell
docker compose down -v
docker compose up -d postgres
```

## 5. Run the multi-agent application

```powershell
python app/loan_agents.py "Which employees are in AI and what does our knowledge base say about RAG?"
```

Try more:

```powershell
python app/loan_agents.py "What is the average salary in the AI department?"
python app/loan_agents.py "Which employee has LLM skills?"
python app/loan_agents.py "When should we use RAG?"
python app/loan_agents.py "Assess loan application 1 and explain the affordability indicators."
```

## 6. Inspect the MCP server directly

Install the MCP CLI if needed through the SDK's `[cli]` extra, then:

```powershell
uv run mcp dev app/mcp_server.py
```

This opens MCP Inspector so you can see the tools and call them without an agent.

## 7. Open the frontend

Start the connected dashboard and API from the project root:

```powershell
py -m uvicorn app.api:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`. The dashboard loads applications from PostgreSQL, persists review state, and searches Chroma. If the database is unavailable, it stays usable with the three seeded demo applications. You can also open `frontend/index.html` directly for demo mode.

The API exposes `/api/health`, `/api/applications`, `/api/applications/{id}/assessment`, `/api/applications/{id}/review`, and `/api/knowledge/search`.

## Mental model

```text
                         ┌──────────────────────┐
                         │      Manager Agent   │
                         └──────────┬───────────┘
                                    │
                         ┌──────────┴───────────┐
                         │                      │
                  SQL Specialist        Knowledge Specialist
                         │                      │
                         └──────────┬───────────┘
                                    │
                             MCP Server (stdio)
                                    │
                         ┌──────────┴──────────┐
                         │                     │
                    PostgreSQL              Chroma
              employees and loan data     vector search
```

The important architecture idea is that the **agents do not connect directly to PostgreSQL/Chroma**. They call MCP tools. The MCP server owns the actual integrations.

## What AI does

- The Manager agent routes questions to the SQL, knowledge, and loan-risk specialists.
- The SQL specialist retrieves employee and department facts through MCP and PostgreSQL.
- The Knowledge specialist searches Chroma and grounds answers in internal guidance.
- The Loan Risk specialist calculates explainable affordability indicators from application data.
- AI does not approve or reject applications, infer protected characteristics, or replace a qualified reviewer. The dashboard's review state, notes, and audit trail remain human-controlled.

## Review workspace features

The connected dashboard at `http://127.0.0.1:8000/` includes:

- **What-if simulator**: tests income, debt, and payment changes without mutating an application.
- **Specialist perspectives**: shows affordability, credit, and stability signals as separate review inputs.
- **Evidence desk**: records uploaded document metadata and queues extraction for an OCR adapter.
- **Repayment watch**: summarizes paid-versus-due events and flags accounts needing follow-up.
- **Fairness check**: reports synthetic operational cohorts for testing; it does not use protected characteristics for lending decisions.
- **Audit trail**: records review changes, document uploads, and reviewer notes.
- **Reviewer notes**: add persistent notes directly to the selected application's audit trail.
- **Knowledge search**: search the local Chroma knowledge base from the review workspace and inspect matched guidance.
- **Queue export**: export the current filtered application queue as CSV for offline review or handoff.
- **Privacy-first operation**: supports local PostgreSQL, Chroma, and Ollama without an OpenAI key.

The API routes are documented automatically at `http://127.0.0.1:8000/docs`. The main routes are `/api/applications`, `/api/applications/{id}/simulate`, `/api/applications/{id}/debate`, `/api/applications/{id}/documents`, `/api/applications/{id}/audit`, `/api/monitoring/repayments`, and `/api/analytics/fairness`.

The project database uses host port `5433` to avoid conflicts with an existing Windows PostgreSQL service on port `5432`; the container still listens on `5432` internally.

Document extraction and repayment-provider webhooks are intentionally adapter points in this MVP. They record and expose the workflow without pretending that an OCR or external banking integration has completed.

## Loan assessment scope

The sample loan specialist is an explainable decision-support workflow. It reports debt-to-income ratio, credit score, and employment-duration indicators from the database. It does not make an automated approval or rejection decision. A production system should add consent, authentication, audit logs, data-quality checks, fairness testing, adverse-action explanations, and qualified human review before being used for lending.
