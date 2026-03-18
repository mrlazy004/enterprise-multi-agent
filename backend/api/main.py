"""
Enterprise Multi-Agent AI System — FastAPI application.
"""
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt

from backend.agents.manager_agent import get_manager_agent
from backend.core.config import settings
from backend.core.logging_config import get_logger, metrics
from backend.models.schemas import (
    ChatRequest,
    ChatResponse,
    HITLApprovalRequest,
    HITLDetail,
    IngestRequest,
    IngestResponse,
    MetricsResponse,
)
from backend.rag.pipeline import get_rag_pipeline

logger = get_logger("api.main")
_start_time = time.time()


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Enterprise Multi-Agent AI…")
    # Warm up the manager (initialises all sub-agents + RAG index check)
    try:
        get_manager_agent()
        logger.info("All agents initialised.")
    except Exception as exc:
        logger.warning(f"Agent warm-up skipped (likely missing Azure creds in dev): {exc}")
    yield
    logger.info("Shutting down Enterprise Multi-Agent AI.")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Enterprise Multi-Agent AI with HR, Finance, Support, and Manager agents.",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Tighten for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


# ── Auth (JWT Bearer) ─────────────────────────────────────────────────────────
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


def create_access_token(data: dict) -> str:
    from datetime import timedelta
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({**data, "exp": expire}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"user_id": user_id, "role": payload.get("role", "employee")}
    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")


# ── Request logging middleware ────────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    rid = str(uuid.uuid4())[:8]
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = (time.perf_counter() - start) * 1000
    logger.info(
        f"[{rid}] {request.method} {request.url.path} → {response.status_code} ({elapsed:.0f}ms)"
    )
    return response


# ── Auth Routes ───────────────────────────────────────────────────────────────
@app.post("/api/auth/token", tags=["auth"])
async def login(form: OAuth2PasswordRequestForm = Depends()):
    # Demo: accept any non-empty credentials; replace with AD/LDAP in production
    if not form.username or not form.password:
        raise HTTPException(status_code=400, detail="Username and password required")
    token = create_access_token({"sub": form.username, "role": "employee"})
    return {"access_token": token, "token_type": "bearer"}


# ── Chat Routes ───────────────────────────────────────────────────────────────
@app.post("/api/chat", response_model=ChatResponse, tags=["agents"])
async def chat(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    session_id = request.session_id or str(uuid.uuid4())
    manager = get_manager_agent()

    try:
        result = await manager.handle(
            user_input=request.message,
            session_id=session_id,
            user_id=current_user["user_id"],
            department=request.department,
        )
    except Exception as exc:
        logger.error(f"Chat handler failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Agent error: {str(exc)}")

    return ChatResponse(
        session_id=session_id,
        response=result["response"],
        agent_type=result["agent_type"],
        steps=result.get("steps", []),
        hitl_required=result.get("hitl_required", False),
        hitl_request_id=result.get("hitl_request_id"),
        sources=[
            {"source": s["source"], "score": str(round(s.get("score", 0), 3))}
            for s in result.get("sources", [])
        ],
        confidence=1.0 - result.get("risk_score", 0),
        created_at=datetime.now(timezone.utc),
    )


# ── HITL Routes ───────────────────────────────────────────────────────────────
@app.get("/api/hitl/pending", response_model=List[HITLDetail], tags=["hitl"])
async def list_pending_hitl(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ("manager", "admin"):
        raise HTTPException(status_code=403, detail="Manager role required")
    manager = get_manager_agent()
    return manager.get_pending_hitl()


@app.get("/api/hitl/{hitl_id}", response_model=HITLDetail, tags=["hitl"])
async def get_hitl(hitl_id: str, current_user: dict = Depends(get_current_user)):
    manager = get_manager_agent()
    req = manager.get_hitl_by_id(hitl_id)
    if not req:
        raise HTTPException(status_code=404, detail="HITL request not found")
    return req


@app.post("/api/hitl/{hitl_id}/resolve", tags=["hitl"])
async def resolve_hitl(
    hitl_id: str,
    body: HITLApprovalRequest,
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role") not in ("manager", "admin"):
        raise HTTPException(status_code=403, detail="Manager role required")
    manager = get_manager_agent()
    try:
        result = await manager.resolve_hitl(
            hitl_id=hitl_id,
            decision=body.decision.value,
            approver_id=current_user["user_id"],
            comment=body.comment,
        )
        return {"success": True, "hitl": result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── Document Ingestion ────────────────────────────────────────────────────────
@app.post("/api/documents/ingest", response_model=IngestResponse, tags=["rag"])
async def ingest_document(
    request: IngestRequest,
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role") not in ("admin",):
        raise HTTPException(status_code=403, detail="Admin role required")
    rag = get_rag_pipeline()
    total_chunks = 0
    for scope in request.agent_scope:
        if request.source_type == "pdf":
            chunks = await rag.ingest_pdf(request.source_path, scope.value)
        elif request.source_type == "csv":
            chunks = await rag.ingest_csv(request.source_path, scope.value)
        else:
            raise HTTPException(status_code=400, detail="source_type must be pdf or csv")
        total_chunks += chunks

    return IngestResponse(
        success=True,
        message="Ingestion complete",
        chunks_indexed=total_chunks,
        source=request.source_path,
    )


# ── Metrics & Health ──────────────────────────────────────────────────────────
@app.get("/api/metrics", response_model=MetricsResponse, tags=["ops"])
async def get_metrics(current_user: dict = Depends(get_current_user)):
    snap = metrics.snapshot()
    return MetricsResponse(
        agent_calls=snap.get("agent_calls", {}),
        errors=snap.get("errors", {}),
        avg_latencies=snap.get("avg_latencies", {}),
        hitl_events=snap.get("hitl_events", 0),
        uptime_seconds=round(time.time() - _start_time, 1),
    )


@app.get("/api/health", tags=["ops"])
async def health():
    return {"status": "ok", "version": settings.APP_VERSION, "ts": datetime.now(timezone.utc)}


@app.get("/", include_in_schema=False)
async def root():
    return {"message": f"{settings.APP_NAME} v{settings.APP_VERSION} — see /api/docs"}
