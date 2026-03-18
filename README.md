# Enterprise Multi-Agent AI System

A production-grade, cloud-native multi-agent AI platform built on **Azure OpenAI**, **LangChain**, and **FastAPI**. Four specialised agents — HR, Finance, Support, and Manager — collaborate to handle enterprise queries with RAG-powered knowledge retrieval, Redis-backed memory, a human-in-the-loop approval workflow, and full observability via Azure Application Insights.

---

## Architecture

```
User / Frontend (React)
        │
        ▼
┌────────────────────┐
│   FastAPI Backend  │  JWT Auth · GZip · Request logging
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│   Manager Agent    │  Query classifier · Orchestrator · HITL gating
└──┬───┬────┬────────┘
   │   │    │
   ▼   ▼    ▼
  HR  Fin  Sup    ← Specialist agents with per-tool risk scoring
   │   │    │
   └───┴────┘
         │
   ┌─────┴──────┐
   │  LangChain │  Tools · Memory · AgentExecutor
   └─────┬──────┘
         │
   ┌─────┴───────────────────────────────────┐
   │            Azure Services               │
   │  OpenAI GPT-4o · AI Search · Redis ·   │
   │  PostgreSQL · App Insights · Storage    │
   └─────────────────────────────────────────┘
```

---

## Features

| Feature | Implementation |
|---|---|
| 4 specialised AI agents | HR, Finance, Support, Manager (orchestrator) |
| Agent orchestration | LangChain `AgentExecutor` with OpenAI Tools |
| Agent-to-agent communication | Manager routes and synthesises sub-agent results |
| Per-agent memory | Redis-backed `ConversationBufferWindowMemory` |
| RAG pipeline | Azure AI Search (vector + semantic hybrid) |
| Document ingestion | PDF, CSV, and database tables |
| LLM backend | Azure OpenAI GPT-4o |
| Backend API | FastAPI with JWT auth, structured logging, Gzip |
| Frontend dashboard | React — chat, approvals queue, metrics |
| Human-in-the-loop | Risk-scored HITL requests with approve/reject UI |
| Monitoring | Azure App Insights + structured JSON logs + in-process metrics |
| Error handling | Per-call try/catch, agent timeout, graceful degradation |
| Deployment | Azure Container Apps via Bicep + GitHub Actions CI/CD |

---

## Project Structure

```
enterprise-multi-agent/
├── backend/
│   ├── agents/
│   │   ├── base_agent.py          # Abstract base — LLM, RAG, memory, risk
│   │   ├── hr_agent.py            # HR tools: policy lookup, PTO, onboarding
│   │   ├── finance_agent.py       # Finance tools: invoices, budgets, expenses
│   │   ├── support_agent.py       # Support tools: tickets, KB search
│   │   └── manager_agent.py       # Orchestrator + HITL store
│   ├── api/
│   │   └── main.py                # FastAPI app — all routes
│   ├── core/
│   │   ├── config.py              # Pydantic settings (env-driven)
│   │   └── logging_config.py      # JSON logging + App Insights + metrics
│   ├── memory/
│   │   └── agent_memory.py        # Redis-backed per-agent memory
│   ├── models/
│   │   ├── database.py            # SQLAlchemy ORM models
│   │   └── schemas.py             # Pydantic request/response schemas
│   └── rag/
│       └── pipeline.py            # Azure AI Search ingest + retrieve
├── frontend/
│   └── src/
│       ├── App.jsx                # Full dashboard: chat, approvals, metrics
│       └── main.jsx
├── data/
│   ├── hr/hr_policies.csv         # Sample HR policies
│   ├── finance/invoices.csv       # Sample invoice data
│   └── support/tickets_history.csv
├── infrastructure/
│   ├── azure/main.bicep           # Full Azure infra as code
│   └── docker/
│       ├── Dockerfile.api
│       ├── Dockerfile.frontend
│       └── nginx.conf
├── tests/
│   └── unit/test_agents.py        # Routing, risk scoring, HITL unit tests
├── .github/workflows/deploy.yml   # CI/CD pipeline
├── docker-compose.yml             # Local dev stack
├── requirements.txt
└── .env.example
```

---

## Quick Start (Local)

### 1. Prerequisites

- Python 3.11+
- Node.js 20+
- Docker Desktop
- Azure subscription with:
  - Azure OpenAI resource (GPT-4o + text-embedding-ada-002 deployments)
  - Azure AI Search resource (Standard tier for semantic search)

### 2. Clone and configure

```bash
git clone https://github.com/your-org/enterprise-multi-agent.git
cd enterprise-multi-agent
cp .env.example .env
# Edit .env with your Azure credentials
```

### 3. Start the full stack with Docker Compose

```bash
docker compose up --build
```

Services started:
- API: http://localhost:8000 (docs at `/api/docs`)
- Frontend: http://localhost:3000
- Redis: localhost:6379
- PostgreSQL: localhost:5432

### 4. Ingest sample documents

```bash
# Ingest HR policies for the HR agent
curl -X POST http://localhost:8000/api/documents/ingest \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "csv",
    "source_path": "data/hr/hr_policies.csv",
    "agent_scope": ["hr"]
  }'

# Ingest Finance data for the Finance agent
curl -X POST http://localhost:8000/api/documents/ingest \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"source_type":"csv","source_path":"data/finance/invoices.csv","agent_scope":["finance"]}'
```

### 5. Test the chat API

```bash
# Get a token (any username/password works in dev mode)
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/token \
  -d "username=alice&password=pass" | jq -r .access_token)

# Chat with the HR agent
curl -X POST http://localhost:8000/api/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"alice","message":"How many PTO days do I have?"}'

# Chat with the Finance agent
curl -X POST http://localhost:8000/api/chat \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"user_id":"alice","message":"Submit invoice INV-2025-099 from Acme Corp for $12,000 - software"}'
```

---

## Deploy to Azure

### One-time setup

```bash
# Login
az login
az account set --subscription YOUR_SUBSCRIPTION_ID

# Create resource group
az group create --name enterprise-ai-rg --location eastus

# Create Azure Container Registry
az acr create --resource-group enterprise-ai-rg \
  --name YOUR_ACR_NAME --sku Basic --admin-enabled true
```

### Deploy infrastructure + apps

```bash
# Deploy Bicep infrastructure
az deployment group create \
  --resource-group enterprise-ai-rg \
  --template-file infrastructure/azure/main.bicep \
  --parameters environment=prod

# Build and push images
az acr build --registry YOUR_ACR_NAME \
  --image enterprise-ai-api:latest \
  --file infrastructure/docker/Dockerfile.api .

az acr build --registry YOUR_ACR_NAME \
  --image enterprise-ai-frontend:latest \
  --file infrastructure/docker/Dockerfile.frontend .
```

After deployment the Bicep outputs print the API and frontend URLs.

### CI/CD (GitHub Actions)

Add these repository secrets in GitHub → Settings → Secrets:

| Secret | Value |
|---|---|
| `AZURE_CREDENTIALS` | Output of `az ad sp create-for-rbac --sdk-auth` |
| `ACR_REGISTRY` | e.g. `myacr.azurecr.io` |

Every push to `main` runs tests → builds Docker images → deploys Bicep → updates Container Apps.

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/auth/token` | Login — returns JWT |
| `POST` | `/api/chat` | Send message to multi-agent system |
| `GET` | `/api/hitl/pending` | List pending approval requests (manager role) |
| `POST` | `/api/hitl/{id}/resolve` | Approve or reject a HITL request |
| `POST` | `/api/documents/ingest` | Ingest PDF/CSV into RAG index (admin) |
| `GET` | `/api/metrics` | Agent call counts, latencies, errors |
| `GET` | `/api/health` | Health check |

Full interactive docs: `http://localhost:8000/api/docs`

---

## Human-in-the-Loop (HITL)

Risk thresholds that automatically trigger HITL approval:

| Scenario | Risk Score | Action |
|---|---|---|
| Termination / harassment mention (HR) | 0.90 | Block, require manager |
| Invoice > $5,000 (Finance) | 0.92 | Block, require CFO |
| Vendor bank account change (Finance) | 0.95 | Block, require CFO |
| Security breach detected (Support) | 0.95 | Escalate, notify security team |
| Budget exceeded (Finance) | 0.80 | Flag, require manager |
| Critical ticket (Support) | 0.75 | Escalate |

HITL requests expire after 1 hour if not resolved. Adjust thresholds via `HITL_HIGH_RISK_THRESHOLD` in `.env`.

---

## Running Tests

```bash
pip install -r requirements.txt pytest pytest-asyncio

# Unit tests only (no Azure required)
pytest tests/unit -v

# With coverage
pytest tests/unit --cov=backend --cov-report=html
```

---

## Extending the System

### Adding a new agent

1. Create `backend/agents/my_agent.py` extending `BaseAgent`
2. Implement `_build_tools()` and `_assess_risk()`
3. Register in `ManagerAgent.__init__()` and `classify_query()`
4. Add RAG scope and ingest relevant documents

### Adding a new tool

```python
from langchain_core.tools import tool
from pydantic import BaseModel, Field

class MyToolInput(BaseModel):
    param: str = Field(..., description="What this parameter does")

@tool(args_schema=MyToolInput)
def my_tool(param: str) -> str:
    """One-line description used by the LLM to decide when to call this tool."""
    return f"Result for {param}"
```

---

## License

MIT — see LICENSE for details.
