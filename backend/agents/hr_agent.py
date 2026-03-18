"""
HR Agent — answers employee questions about policies, benefits,
onboarding, PTO, payroll, and compliance.
"""
from typing import List, Tuple
from langchain_core.tools import tool, BaseTool
from langchain_core.pydantic_v1 import BaseModel, Field

from backend.agents.base_agent import BaseAgent
from backend.core.logging_config import get_logger

logger = get_logger("agent.hr")


# ── Tool input schemas ────────────────────────────────────────────────────────
class PolicyLookupInput(BaseModel):
    topic: str = Field(..., description="HR policy topic, e.g. 'parental leave', 'expense reimbursement'")


class PTOCalculatorInput(BaseModel):
    employee_id: str = Field(..., description="Employee ID")
    days_requested: int = Field(..., description="Number of PTO days requested")


class OnboardingStatusInput(BaseModel):
    employee_id: str = Field(..., description="New hire employee ID")


# ── Tools ─────────────────────────────────────────────────────────────────────
@tool(args_schema=PolicyLookupInput)
def lookup_hr_policy(topic: str) -> str:
    """Look up an HR policy by topic. Returns the relevant policy text."""
    # In production this would query the HR system API or the RAG pipeline
    mock_policies = {
        "parental leave": "Employees receive 16 weeks paid parental leave after 1 year of service.",
        "pto": "Full-time employees accrue 1.5 PTO days per month (18/year). Unused PTO rolls over up to 30 days.",
        "expense reimbursement": "Business expenses under $500 are auto-approved. Above $500 requires manager sign-off.",
        "remote work": "Employees may work remotely up to 3 days per week with manager approval.",
        "health insurance": "Company covers 80% of health insurance premium for employees and 60% for dependents.",
    }
    key = topic.lower()
    for policy_key, policy_text in mock_policies.items():
        if policy_key in key or key in policy_key:
            return f"POLICY — {policy_key.title()}:\n{policy_text}"
    return f"No specific policy found for '{topic}'. Please contact HR directly at hr@company.com."


@tool(args_schema=PTOCalculatorInput)
def calculate_pto_balance(employee_id: str, days_requested: int) -> str:
    """Calculate PTO balance and whether a request can be approved."""
    # Mock — replace with HRIS API call
    mock_balances = {"EMP001": 12, "EMP002": 5, "EMP003": 20}
    balance = mock_balances.get(employee_id, 8)  # default 8 days
    remaining = balance - days_requested
    if remaining >= 0:
        return (
            f"Employee {employee_id}: Current balance = {balance} days. "
            f"Requesting {days_requested} days. "
            f"Remaining after approval = {remaining} days. ✓ Request can be approved."
        )
    return (
        f"Employee {employee_id}: Insufficient PTO. "
        f"Balance = {balance} days, requesting {days_requested} days. "
        f"Shortfall = {abs(remaining)} days. Request CANNOT be auto-approved."
    )


@tool(args_schema=OnboardingStatusInput)
def get_onboarding_status(employee_id: str) -> str:
    """Retrieve onboarding checklist status for a new hire."""
    # Mock — replace with HRIS/onboarding system
    return (
        f"Onboarding for {employee_id}:\n"
        "✓ Offer letter signed\n"
        "✓ Background check cleared\n"
        "✓ IT accounts provisioned\n"
        "◯ Benefits enrollment (due in 3 days)\n"
        "◯ Security training (due in 5 days)\n"
        "◯ Manager 1:1 scheduled"
    )


# ── HR Agent ─────────────────────────────────────────────────────────────────
class HRAgent(BaseAgent):
    agent_type = "hr"
    rag_scope = "hr"
    system_prompt = """You are the Enterprise HR Assistant. Your role is to help employees with:
- HR policies (leave, benefits, expense reimbursement, remote work, health insurance)
- PTO requests and balances
- Onboarding status and checklists
- Payroll and compensation questions
- Compliance and code of conduct

Guidelines:
- Always be empathetic and professional
- Cite the specific policy source when answering policy questions
- Flag any PTO requests exceeding employee balance as requiring manual review
- For sensitive issues (discrimination, harassment, termination), always recommend speaking with HR directly
- Never share one employee's personal data with another employee"""

    def _build_tools(self) -> List[BaseTool]:
        return [lookup_hr_policy, calculate_pto_balance, get_onboarding_status]

    def _assess_risk(self, user_input: str, response: str) -> Tuple[float, str]:
        text = (user_input + " " + response).lower()
        high_risk_keywords = [
            "termination", "terminating", "fire", "layoff", "discrimination",
            "harassment", "legal action", "lawsuit", "severance",
        ]
        medium_risk_keywords = ["salary adjustment", "promotion", "demotion", "investigation"]

        for kw in high_risk_keywords:
            if kw in text:
                return 0.9, f"hr_sensitive_action:{kw}"

        for kw in medium_risk_keywords:
            if kw in text:
                return 0.7, f"hr_review_action:{kw}"

        return 0.1, "hr_standard_query"
