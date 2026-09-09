from dotenv import load_dotenv
load_dotenv()  # must run before any other import that reads env vars at import time (e.g. API keys)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.db.database import init_db
from app.api.routes import targets, evidence, scoring, contradictions, gaps, narrative, narration, agent, momentum, graph
from app.config import DISEASE_NAME, DISEASE_EFO_ID


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Evidence-Guided Target Prioritization & Research Gap Identification",
    description=f"Prototype scoped to {DISEASE_NAME} ({DISEASE_EFO_ID}). "
                "Deterministic modules compute scores; agentic layer orchestrates and explains.",
    version="0.1.0",
    lifespan=lifespan,
)

# Phase 10 (frontend): the React/Vite dev server runs on a different origin
# (localhost:5173 or :8443, depending on how it's started — see
# figma_frontend/figma_extracted/vite.config.ts) than this API (localhost:8000),
# so the browser's same-origin policy blocks fetch() calls without this.
# Explicit origins only (not "*") since credentials aren't used here and an
# explicit allowlist is the honest, minimal-surface choice for a prototype
# that's about to start accepting real cross-origin requests for the first
# time — extend this list if the frontend is served from another port.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",  # default Vite port
        "http://localhost:8443", "http://127.0.0.1:8443",  # this project's configured Vite port
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(targets.router)
app.include_router(evidence.router)
app.include_router(scoring.router)
app.include_router(contradictions.router)
app.include_router(gaps.router)
app.include_router(narrative.router)
app.include_router(narration.router)
app.include_router(agent.router)
app.include_router(momentum.router)
app.include_router(graph.router)


@app.get("/")
def root():
    return {
        "project": "Evidence-Guided Target Prioritization & Research Gap Identification",
        "disease": DISEASE_NAME,
        "disease_efo_id": DISEASE_EFO_ID,
        "docs": "/docs",
    }
