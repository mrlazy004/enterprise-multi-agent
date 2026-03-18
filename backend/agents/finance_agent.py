"""
Finance Agent — handles invoice processing, expense approvals,
budget queries, and financial reporting.
"""
from typing import List, Tuple
from langchain_core.tools import tool, BaseTool
from langchain_core.pydantic_v1 import BaseModel, Field

from backend.agents.base_agent import BaseAgent
from backend.core.config import settings
from backend.core.logging_config import get_logger

logger = get_logger("agent.finance")


# ── Tool input schemas ────────────────────────────────────────────────────────
class InvoiceInput(BaseModel):
    invoice_id: str = Field(..., description="Invoice reference number")
    vendor: str = Field(..., description="Vendor/supplier name")
    amount: float = Field(..., description="Invoice amount in USD")
    category: str = Field(..., description="Expense category e.g. software, travel, office")


class ExpenseQueryInput(BaseModel):
    department: str = Field(..., description="Department name")
    period: str = Field(..., description="Time period e.g. 'Q1 2025', 'March 2025'")


class BudgetCheckInput(BaseModel):
    department: str = Field(..., description="Department name")
    category: str = Field(..., description="Budget category")
    amount: float = Field(..., description="Amount to check against budget")


# ── Tools ─────────────────────────────────────────────────────────────────────
@tool(args_schema=InvoiceInput)
def process_invoice(invoice_id: str, vendor: str, amount: float, category: str) -> str:
    """
    Process an invoice submission. Returns approval status.
    Amounts above the threshold require HITL approval.
    """
    threshold = settings.FINANCE_APPROVAL_THRESHOLD
    if amount <= threshold:
        return (
            f"Invoice {invoice_id} from {vendor} for ${amount:,.2f} ({category}): "
            f"AUTO-APPROVED. Will be processed in next payment run."
        )
    return (
        f"Invoice {invoice_id} from {vendor} for ${amount:,.2f} ({category}): "
        f"PENDING APPROVAL. Amount exceeds ${threshold:,.0f} threshold. "
        f"Sent to Finance Manager for review."
    )


@tool(args_schema=ExpenseQueryInput)
def get_expense_report(department: str, period: str) -> str:
    """Generate an expense summary report for a department and time period."""
    # Mock — replace with ERP/accounting system API
    mock_data = {
        "engineering": {"Q1 2025": {"software": 12000, "travel": 4500, "office": 800}},
        "sales": {"Q1 2025": {"travel": 28000, "marketing": 15000, "entertainment": 3200}},
        "hr": {"Q1 2025": {"training": 8000, "recruiting": 22000, "office": 600}},
    }
    dept_key = department.lower()
    data = mock_data.get(dept_key, {}).get(period, {})
    if not data:
        return f"No expense data found for {department} / {period}."
    total = sum(data.values())
    lines = "\n".join(f"  {cat.title()}: ${amt:,.0f}" for cat, amt in data.items())
    return f"Expense Report — {department.title()} ({period}):\n{lines}\n  ────────\n  Total: ${total:,.0f}"


@tool(args_schema=BudgetCheckInput)
def check_budget_availability(department: str, category: str, amount: float) -> str:
    """Check if a department has sufficient budget for an expense."""
    # Mock budget data
    mock_budgets = {
        "engineering": {"software": 50000, "travel": 20000, "office": 5000},
        "sales": {"travel": 100000, "marketing": 60000, "entertainment": 10000},
        "hr": {"training": 30000, "recruiting": 80000},
    }
    mock_spent = {
        "engineering": {"software": 12000, "travel": 4500, "office": 800},
        "sales": {"travel": 28000, "marketing": 15000, "entertainment": 3200},
        "hr": {"training": 8000, "recruiting": 22000},
    }
    dept_key = department.lower()
    cat_key = category.lower()
    budget = mock_budgets.get(dept_key, {}).get(cat_key, 0)
    spent = mock_spent.get(dept_key, {}).get(cat_key, 0)
    remaining = budget - spent
    can_approve = remaining >= amount

    status = "✓ SUFFICIENT" if can_approve else "✗ INSUFFICIENT"
    return (
        f"Budget Check — {department.title()} / {category.title()}:\n"
        f"  Annual budget: ${budget:,.0f}\n"
        f"  Spent YTD: ${spent:,.0f}\n"
        f"  Remaining: ${remaining:,.0f}\n"
        f"  Requested: ${amount:,.0f}\n"
        f"  Status: {status}"
    )


# ── Finance Agent ─────────────────────────────────────────────────────────────
class FinanceAgent(BaseAgent):
    agent_type = "finance"
    rag_scope = "finance"
    system_prompt = """You are the Enterprise Finance Assistant. You help with:
- Invoice submission and approval status
- Expense report queries and generation
- Budget availability checks
- Purchase order requests
- Reimbursement status tracking
- Financial policy questions

Guidelines:
- Always quote exact amounts and reference invoice/PO numbers
- Flag any amounts above $5,000 as requiring management approval
- Never approve expenses that would exceed department budget
- For financial discrepancies or fraud concerns, escalate to the Manager Agent immediately
- All approved invoices must reference a valid cost center and budget category"""

    def _build_tools(self) -> List[BaseTool]:
        return [process_invoice, get_expense_report, check_budget_availability]

    def _assess_risk(self, user_input: str, response: str) -> Tuple[float, str]:
        text = (user_input + " " + response).lower()

        # Extract amount from response heuristically
        import re
        amounts = re.findall(r"\$([0-9,]+(?:\.[0-9]{2})?)", response)
        for amt_str in amounts:
            try:
                amt = float(amt_str.replace(",", ""))
                if amt >= settings.FINANCE_APPROVAL_THRESHOLD:
                    return 0.92, f"finance_large_transaction:{amt}"
            except ValueError:
                pass

        fraud_keywords = ["duplicate invoice", "vendor change", "bank account change", "urgent payment"]
        for kw in fraud_keywords:
            if kw in text:
                return 0.95, f"finance_fraud_risk:{kw}"

        if "budget" in text and "exceeded" in text:
            return 0.80, "finance_budget_exceeded"

        return 0.15, "finance_standard_query"
