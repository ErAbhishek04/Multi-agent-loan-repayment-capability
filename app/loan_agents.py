from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from agents import Agent, OpenAIChatCompletionsModel, Runner, set_tracing_disabled
from agents.mcp import MCPServerStdio
from openai import AsyncOpenAI

load_dotenv()
set_tracing_disabled(True)

BASE_DIR = Path(__file__).resolve().parent
SERVER_FILE = BASE_DIR / "mcp_server.py"


def local_model() -> OpenAIChatCompletionsModel:
    client = AsyncOpenAI(
        base_url=os.getenv("LLM_BASE_URL", "http://127.0.0.1:11434/v1").replace("://localhost:", "://127.0.0.1:"),
        api_key=os.getenv("LLM_API_KEY", "ollama"),
    )
    return OpenAIChatCompletionsModel(
        model=os.getenv("LLM_MODEL", "llama3.2"),
        openai_client=client,
    )


def build_agents(server: MCPServerStdio) -> Agent:
    model = local_model()
    sql_agent = Agent(
        name="SQL Specialist",
        instructions=(
            "You answer questions about structured employee data. "
            "Use the PostgreSQL MCP tools when the question needs employee records "
            "or department salary statistics. Never invent database facts."
        ),
        mcp_servers=[server],
        model=model,
    )

    rag_agent = Agent(
        name="Knowledge Specialist",
        instructions=(
            "You answer questions about company knowledge and technical guidance. "
            "Use the Chroma semantic_search MCP tool for knowledge retrieval. "
            "Ground claims in retrieved documents and say when the knowledge base is empty."
        ),
        mcp_servers=[server],
        model=model,
    )

    loan_agent = Agent(
        name="Loan Risk Specialist",
        instructions=(
            "You analyze loan applications using the assess_loan_application MCP tool. "
            "Call the MCP tool before answering any application-specific question. "
            "Use only values returned by that tool; never infer, estimate, assume, or "
            "invent credit score, income, employment history, loan amount, loan term, "
            "risk level, or approval status. If the tool errors, say that the application "
            "could not be retrieved and stop without an assessment. If the application is "
            "not found, report that exact status and request a valid application ID. "
            "Always cite the returned inputs, debt-to-income ratio, and each indicator. "
            "Explain that the result is decision support only: never claim to approve, "
            "reject, or predict a person's worthiness. Flag missing applications and "
            "recommend qualified human review, especially for borderline results."
        ),
        mcp_servers=[server],
        model=model,
    )

    manager = Agent(
        name="Manager",
        instructions=(
            "You are the user-facing manager for a company assistant. "
            "Delegate database questions to the SQL Specialist and company-knowledge "
            "questions to the Knowledge Specialist. Delegate loan application assessment "
            "to the Loan Risk Specialist. For questions that require multiple specialists, "
            "call them and combine their results. Keep the final answer concise, distinguish "
            "database facts from knowledge-base facts, and preserve the loan specialist's "
            "human-review and decision-support boundary. Never invent or assume applicant "
            "data. If a specialist reports a tool error, report the limitation rather than "
            "retrying with fabricated or hypothetical values."
        ),
        model=model,
        tools=[
            sql_agent.as_tool(
                tool_name="sql_specialist",
                tool_description="Answer questions using PostgreSQL employee data.",
            ),
            rag_agent.as_tool(
                tool_name="knowledge_specialist",
                tool_description="Answer questions using Chroma company knowledge.",
            ),
            loan_agent.as_tool(
                tool_name="loan_risk_specialist",
                tool_description="Analyze a loan application's affordability indicators.",
            ),
        ],
    )
    return manager


async def main() -> None:
    async with MCPServerStdio(
        name="employee-data-server",
        client_session_timeout_seconds=60,
        params={
            "command": sys.executable,
            "args": [str(SERVER_FILE)],
        },
    ) as server:
        manager = build_agents(server)
        question = " ".join(sys.argv[1:]).strip()
        if not question:
            question = (
                "Which AI employees earn more than 1.7 million, and what does the knowledge base "
                "say about when we should use RAG?"
            )

        result = await Runner.run(manager, question)
        print("\nFINAL ANSWER\n")
        print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())
