"""
Manager Agent — the orchestrator.
Routes queries to specialist agents, synthesizes responses,
handles escalations, and triggers HITL when required.
"""
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.tools import tool, BaseTool
from langchain_openai import AzureChatOpenAI
from pydantic import BaseModel, Field

from backend.agents.base_agent import BaseAgent
from backend.agents.hr_agent import HRAgent
from backend.agents.finance_agent import FinanceAgent
from backend.agents.support_agent import SupportAgent
from backend.core.config import settings
from backend.core.logging_config import get_logger, metrics
from backend.memory.agent_memory import get_agent_memory

logger = get_logger("agent.manager")


# ── Routing classifier ────────────────────────────────────────────────────────
ROUTING_KEYWORDS = {
    "hr": [
        "pto", "leave", "vacation", "sick", "onboarding", "benefits", "payroll",
        "salary", "policy", "remote work", "parental", "health insurance", "performance review",
    ],
    "finance": [
        "invoice", "expense", "reimbursement", "budget", "purchase", "vendor",
        "payment", "cost", "price", "billing", "receipt", "financial",
    ],
    "support": [
        "ticket", "vpn", "laptop", "email", "wifi", "wi-fi", "access", "password",
        "error", "broken", "not working", "crash", "slow", "install", "software",
        "hardware", "network", "internet", "printer",
    ],
}


def classify_query(text: str) -> str:
    text_lower = text.lower()
    scores = {agent: 0 for agent in ROUTING_KEYWORDS}
    for agent, keywords in ROUTING_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                scores[agent] += 1
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "general"
    return best


# ── HITL store (in-process; replace with DB in prod) ─────────────────────────
_hitl_store: Dict[str, Dict] = {}


class ManagerAgent:
    """
    Orchestrator that:
    1. Classifies the incoming query
    2. Delegates to the correct specialist agent
    3. Reviews the response
    4. Creates HITL approval requests for high-risk actions
    5. Returns consolidated results
    """

    def __init__(self):
        self.logger = logger
        self.hr_agent = HRAgent()
        self.finance_agent = FinanceAgent()
        self.support_agent = SupportAgent()
        self.agents = {
            "hr": self.hr_agent,
            "finance": self.finance_agent,
            "support": self.support_agent,
        }
        self.llm = AzureChatOpenAI(
            azure_deployment=settings.AZURE_OPENAI_DEPLOYMENT_NAME,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            temperature=0.1,
            max_tokens=1024,
        )

    # ── Main orchestration entry point ────────────────────────────────────────
    async def handle(
        self,
        user_input: str,
        session_id: str,
        user_id: str,
        department: Optional[str] = None,
    ) -> Dict[str, Any]:
        import time
        start = time.perf_counter()

        self.logger.info(f"Manager routing query for session={session_id}")

        # 1. Classify
        target_agent_key = classify_query(user_input)
        if target_agent_key == "general" and department:
            target_agent_key = department.lower() if department.lower() in self.agents else "support"

        # 2. Delegate
        steps = []
        if target_agent_key in self.agents:
            agent = self.agents[target_agent_key]
            agent_result = await agent.run(user_input, session_id)
            steps.append({
                "agent": target_agent_key,
                "input": user_input,
                "output": agent_result["response"],
                "tool_calls": agent_result.get("intermediate_steps", []),
                "latency_ms": agent_result.get("latency_ms", 0),
            })
        else:
            # General question — answer directly
            from langchain_core.messages import HumanMessage
            response = await self.llm.ainvoke([HumanMessage(content=user_input)])
            agent_result = {
                "response": response.content,
                "agent_type": "manager",
                "sources": [],
                "hitl_required": False,
                "risk_score": 0.0,
                "action_type": "general_query",
                "latency_ms": 0,
            }
            target_agent_key = "manager"

        # 3. HITL check
        hitl_request_id = None
        if agent_result.get("hitl_required"):
            hitl_request_id = await self._create_hitl_request(
                session_id=session_id,
                user_id=user_id,
                agent_type=target_agent_key,
                action_type=agent_result.get("action_type", "unknown"),
                payload={
                    "user_input": user_input,
                    "agent_response": agent_result["response"],
                },
                risk_score=agent_result.get("risk_score", 0),
            )
            metrics.record_hitl()

        elapsed = (time.perf_counter() - start) * 1000
        return {
            "session_id": session_id,
            "response": agent_result["response"],
            "agent_type": target_agent_key,
            "steps": steps,
            "sources": agent_result.get("sources", []),
            "hitl_required": agent_result.get("hitl_required", False),
            "hitl_request_id": hitl_request_id,
            "risk_score": agent_result.get("risk_score", 0),
            "total_latency_ms": round(elapsed, 1),
        }

    # ── HITL management ───────────────────────────────────────────────────────
    async def _create_hitl_request(
        self,
        session_id: str,
        user_id: str,
        agent_type: str,
        action_type: str,
        payload: Dict,
        risk_score: float,
    ) -> str:
        hitl_id = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.HITL_APPROVAL_TIMEOUT)
        _hitl_store[hitl_id] = {
            "id": hitl_id,
            "session_id": session_id,
            "user_id": user_id,
            "agent_type": agent_type,
            "action_type": action_type,
            "payload": payload,
            "risk_score": risk_score,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        self.logger.info(
            f"HITL request created: {hitl_id} | agent={agent_type} | risk={risk_score:.2f}"
        )
        return hitl_id

    async def resolve_hitl(
        self,
        hitl_id: str,
        decision: str,          # "approved" | "rejected"
        approver_id: str,
        comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        if hitl_id not in _hitl_store:
            raise ValueError(f"HITL request {hitl_id} not found")
        request = _hitl_store[hitl_id]
        if request["status"] != "pending":
            raise ValueError(f"HITL request {hitl_id} already resolved: {request['status']}")

        request["status"] = decision
        request["approver_id"] = approver_id
        request["approver_comment"] = comment
        request["resolved_at"] = datetime.now(timezone.utc).isoformat()

        self.logger.info(f"HITL {hitl_id} resolved: {decision} by {approver_id}")
        return request

    def get_pending_hitl(self) -> List[Dict]:
        return [r for r in _hitl_store.values() if r["status"] == "pending"]

    def get_hitl_by_id(self, hitl_id: str) -> Optional[Dict]:
        return _hitl_store.get(hitl_id)


# ── Singleton ─────────────────────────────────────────────────────────────────
_manager: Optional[ManagerAgent] = None


def get_manager_agent() -> ManagerAgent:
    global _manager
    if _manager is None:
        _manager = ManagerAgent()
    return _manager
