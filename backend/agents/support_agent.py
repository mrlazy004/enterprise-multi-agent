"""
Support Agent — creates, routes, and resolves IT/operations support tickets.
"""
import uuid
from typing import List, Tuple
from langchain_core.tools import tool, BaseTool
from langchain_core.pydantic_v1 import BaseModel, Field

from backend.agents.base_agent import BaseAgent
from backend.core.logging_config import get_logger

logger = get_logger("agent.support")


# ── Tool input schemas ────────────────────────────────────────────────────────
class CreateTicketInput(BaseModel):
    title: str = Field(..., description="Short ticket title")
    description: str = Field(..., description="Detailed issue description")
    category: str = Field(..., description="Category: IT, facilities, security, access")
    priority: str = Field(..., description="Priority: low, medium, high, critical")
    reporter_id: str = Field(..., description="Employee ID of the reporter")


class TicketStatusInput(BaseModel):
    ticket_id: str = Field(..., description="Ticket ID e.g. TKT-12345")


class KBSearchInput(BaseModel):
    query: str = Field(..., description="Search query for the knowledge base")


# ── Tools ─────────────────────────────────────────────────────────────────────
@tool(args_schema=CreateTicketInput)
def create_support_ticket(
    title: str, description: str, category: str, priority: str, reporter_id: str
) -> str:
    """Create a new support ticket in the ticketing system."""
    ticket_id = f"TKT-{uuid.uuid4().hex[:5].upper()}"
    sla_map = {"critical": "4 hours", "high": "8 hours", "medium": "2 business days", "low": "5 business days"}
    sla = sla_map.get(priority.lower(), "2 business days")

    # Mock — replace with ServiceNow/Jira API call
    return (
        f"Ticket created successfully!\n"
        f"  ID: {ticket_id}\n"
        f"  Title: {title}\n"
        f"  Category: {category}\n"
        f"  Priority: {priority.upper()}\n"
        f"  Reporter: {reporter_id}\n"
        f"  SLA: {sla}\n"
        f"  Status: OPEN — assigned to {category.upper()} team"
    )


@tool(args_schema=TicketStatusInput)
def get_ticket_status(ticket_id: str) -> str:
    """Get the current status of a support ticket."""
    # Mock — replace with ticketing system API
    mock_statuses = {
        "TKT-A1B2C": {"status": "In Progress", "assignee": "John Smith", "updated": "2 hours ago"},
        "TKT-D3E4F": {"status": "Resolved", "assignee": "Jane Doe", "resolved": "Yesterday"},
    }
    info = mock_statuses.get(ticket_id.upper(), {
        "status": "Open", "assignee": "Unassigned", "updated": "Just now"
    })
    lines = "\n".join(f"  {k.title()}: {v}" for k, v in info.items())
    return f"Ticket {ticket_id}:\n{lines}"


@tool(args_schema=KBSearchInput)
def search_knowledge_base(query: str) -> str:
    """Search the IT knowledge base for troubleshooting guides and FAQs."""
    # Mock — in production this calls the RAG pipeline directly
    mock_kb = {
        "vpn": "VPN Troubleshooting: 1) Check internet connectivity 2) Restart VPN client 3) Clear DNS cache (ipconfig /flushdns) 4) Contact IT if issue persists (ext. 5555).",
        "password": "Password Reset: Visit https://resetpw.company.com or call IT helpdesk at ext. 5555. Resets take effect within 5 minutes.",
        "laptop": "Laptop issues: Run hardware diagnostics (F12 at boot), check device manager, update drivers. For physical damage, submit a hardware replacement ticket.",
        "email": "Email issues: Check spam folder, verify account not locked (https://myaccount.company.com), clear Outlook cache. For access issues contact IT.",
        "wifi": "Wi-Fi connectivity: Forget and rejoin 'CompanyCorp-Secure' network. Password is on the intranet. Enable 802.1x authentication.",
    }
    query_lower = query.lower()
    for kw, solution in mock_kb.items():
        if kw in query_lower:
            return f"KB Article — {kw.upper()}:\n{solution}"
    return (
        f"No KB article found for '{query}'. "
        "A ticket has been flagged for manual review by the support team."
    )


# ── Support Agent ─────────────────────────────────────────────────────────────
class SupportAgent(BaseAgent):
    agent_type = "support"
    rag_scope = "support"
    system_prompt = """You are the Enterprise IT & Operations Support Assistant. You help with:
- Creating and tracking support tickets
- IT troubleshooting (VPN, email, laptop, Wi-Fi, software access)
- Facilities requests
- Security incident reporting
- Knowledge base search

Guidelines:
- Always try to resolve the issue with knowledge base articles first before creating a ticket
- Assign correct priority: critical = system down/security breach, high = major workflow blocked,
  medium = degraded service, low = minor issue
- For security incidents (suspected breach, malware, phishing), immediately escalate to CRITICAL
  and notify the security team
- Include SLA timelines in every ticket created
- Check for duplicate tickets before creating a new one"""

    def _build_tools(self) -> List[BaseTool]:
        return [create_support_ticket, get_ticket_status, search_knowledge_base]

    def _assess_risk(self, user_input: str, response: str) -> Tuple[float, str]:
        text = (user_input + " " + response).lower()
        critical_keywords = [
            "security breach", "ransomware", "malware", "phishing attack",
            "data leak", "unauthorized access", "system compromise",
        ]
        for kw in critical_keywords:
            if kw in text:
                return 0.95, f"support_security_incident:{kw}"

        if "critical" in text and "ticket" in text:
            return 0.75, "support_critical_ticket"

        return 0.1, "support_standard_ticket"
