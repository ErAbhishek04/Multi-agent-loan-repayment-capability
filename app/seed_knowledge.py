from __future__ import annotations

import os

from dotenv import load_dotenv
import chromadb

load_dotenv()

path = os.getenv("CHROMA_PATH", "./chroma_data")
client = chromadb.PersistentClient(path=path)
collection = client.get_or_create_collection(name="company_knowledge")

items = [
    (
        "rag-001",
        "The AI department works mainly on machine learning, NLP, computer vision, and LLM applications.",
        "engineering-handbook",
    ),
    (
        "rag-002",
        "The Platform department owns backend services, APIs, PostgreSQL infrastructure, and internal developer tooling.",
        "engineering-handbook",
    ),
    (
        "rag-003",
        "The company uses Python, FastAPI, PostgreSQL, Docker, vector databases, and cloud services in several AI products.",
        "technology-overview",
    ),
    (
        "rag-004",
        "LLM applications should use retrieval-augmented generation when answers need grounding in internal company knowledge.",
        "ai-guidelines",
    ),
]

for doc_id, document, source in items:
    collection.upsert(ids=[doc_id], documents=[document], metadatas=[{"source": source}])

print(f"Seeded {len(items)} documents into Chroma at {path}")
