"""
Unit tests for agent routing, risk scoring, and HITL logic.
Run with: pytest tests/unit -v
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Test: query classifier ────────────────────────────────────────────────────
from backend.agents.manager_agent import classify_query

class TestQueryClassifier:
    def test_hr_keywords(self):
        assert classify_query("How many PTO days do I have left?") == "hr"
        assert classify_query("What is the parental leave policy?") == "hr"
        assert classify_query("When is my performance review?") == "hr"

    def test_finance_keywords(self):
        assert classify_query("I need to submit an invoice for $1200") == "finance"
        assert classify_query("What is my department budget for travel?") == "finance"
        assert classify_query("Can I get reimbursed for this expense?") == "finance"

    def test_support_keywords(self):
        assert classify_query("My VPN is not working") == "support"
        assert classify_query("I need to reset my password") == "support"
        assert classify_query("Create a ticket for broken laptop") == "support"

    def test_general_fallback(self):
        assert classify_query("Hello, who are you?") == "general"
        assert classify_query("What is 2 + 2?") == "general"


# ── Test: HR agent risk scoring ───────────────────────────────────────────────
from backend.agents.hr_agent import HRAgent

class TestHRAgentRisk:
    def setup_method(self):
        with patch("backend.agents.base_agent.get_rag_pipeline"):
            with patch("backend.agents.base_agent.AzureChatOpenAI"):
                self.agent = HRAgent.__new__(HRAgent)
                self.agent.logger = MagicMock()
                self.agent._tools = []

    def test_high_risk_termination(self):
        score, action = self.agent._assess_risk("terminate employee EMP001", "")
        assert score >= 0.85
        assert "termination" in action or "terminate" in action

    def test_high_risk_harassment(self):
        score, action = self.agent._assess_risk("harassment complaint filed", "")
        assert score >= 0.85

    def test_low_risk_pto(self):
        score, action = self.agent._assess_risk("how many PTO days do I have?", "You have 8 days remaining.")
        assert score < 0.5
        assert action == "hr_standard_query"


# ── Test: Finance agent risk scoring ─────────────────────────────────────────
from backend.agents.finance_agent import FinanceAgent

class TestFinanceAgentRisk:
    def setup_method(self):
        with patch("backend.agents.base_agent.get_rag_pipeline"):
            with patch("backend.agents.base_agent.AzureChatOpenAI"):
                self.agent = FinanceAgent.__new__(FinanceAgent)
                self.agent.logger = MagicMock()
                self.agent._tools = []

    def test_large_transaction_triggers_hitl(self):
        score, action = self.agent._assess_risk(
            "Process this invoice",
            "Invoice INV-001 for $12,500.00 — PENDING APPROVAL"
        )
        assert score >= 0.85
        assert "finance_large_transaction" in action

    def test_fraud_keyword_triggers_hitl(self):
        score, action = self.agent._assess_risk(
            "vendor wants to change bank account",
            "The vendor has requested a bank account change"
        )
        assert score >= 0.90

    def test_small_invoice_auto_approved(self):
        score, action = self.agent._assess_risk(
            "Submit invoice for $200",
            "Invoice for $200.00: AUTO-APPROVED."
        )
        assert score < 0.5


# ── Test: Support agent risk scoring ─────────────────────────────────────────
from backend.agents.support_agent import SupportAgent

class TestSupportAgentRisk:
    def setup_method(self):
        with patch("backend.agents.base_agent.get_rag_pipeline"):
            with patch("backend.agents.base_agent.AzureChatOpenAI"):
                self.agent = SupportAgent.__new__(SupportAgent)
                self.agent.logger = MagicMock()
                self.agent._tools = []

    def test_security_breach_critical(self):
        score, action = self.agent._assess_risk("I think we have a security breach", "")
        assert score >= 0.90
        assert "security_incident" in action

    def test_standard_ticket_low_risk(self):
        score, action = self.agent._assess_risk("My printer is not working", "Ticket TKT-001 created.")
        assert score < 0.5


# ── Test: HITL store ──────────────────────────────────────────────────────────
import asyncio
from backend.agents.manager_agent import ManagerAgent

class TestHITLManager:
    def setup_method(self):
        with patch("backend.agents.manager_agent.HRAgent"):
            with patch("backend.agents.manager_agent.FinanceAgent"):
                with patch("backend.agents.manager_agent.SupportAgent"):
                    with patch("backend.agents.manager_agent.AzureChatOpenAI"):
                        self.manager = ManagerAgent.__new__(ManagerAgent)
                        self.manager.logger = MagicMock()

    def test_create_and_resolve_hitl(self):
        async def run():
            hitl_id = await self.manager._create_hitl_request(
                session_id="sess-123",
                user_id="emp-001",
                agent_type="finance",
                action_type="finance_large_transaction:8000",
                payload={"user_input": "process $8000 invoice"},
                risk_score=0.92,
            )
            assert hitl_id is not None
            req = self.manager.get_hitl_by_id(hitl_id)
            assert req["status"] == "pending"
            assert req["risk_score"] == 0.92

            resolved = await self.manager.resolve_hitl(
                hitl_id=hitl_id,
                decision="approved",
                approver_id="manager-001",
                comment="Verified with vendor",
            )
            assert resolved["status"] == "approved"
            assert resolved["approver_id"] == "manager-001"

        asyncio.get_event_loop().run_until_complete(run())

    def test_double_resolve_raises(self):
        async def run():
            hitl_id = await self.manager._create_hitl_request(
                session_id="sess-456", user_id="emp-002",
                agent_type="hr", action_type="termination",
                payload={}, risk_score=0.95,
            )
            await self.manager.resolve_hitl(hitl_id, "rejected", "mgr-001")
            with pytest.raises(ValueError, match="already resolved"):
                await self.manager.resolve_hitl(hitl_id, "approved", "mgr-002")

        asyncio.get_event_loop().run_until_complete(run())
