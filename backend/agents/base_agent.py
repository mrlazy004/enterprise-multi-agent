"""
Abstract base for all enterprise agents.
Provides LLM init, RAG retrieval, memory, and HITL risk checking.
"""
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import BaseTool
from langchain_openai import AzureChatOpenAI

from backend.core.config import settings
from backend.core.logging_config import get_logger, log_agent_call, metrics
from backend.memory.agent_memory import AgentMemory, get_agent_memory
from backend.rag.pipeline import RAGPipeline, get_rag_pipeline


class BaseAgent(ABC):
    agent_type: str = "base"
    rag_scope: str = "general"
    system_prompt: str = "You are a helpful enterprise AI assistant."

    def __init__(self):
        self.logger = get_logger(f"agent.{self.agent_type}")
        self.rag = get_rag_pipeline()
        self.llm = AzureChatOpenAI(
            azure_deployment=settings.AZURE_OPENAI_DEPLOYMENT_NAME,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            temperature=0.1,
            max_tokens=2048,
            request_timeout=settings.AGENT_TIMEOUT_SECONDS,
        )
        self._tools: List[BaseTool] = self._build_tools()

    # ── Abstract ──────────────────────────────────────────────────────────────
    @abstractmethod
    def _build_tools(self) -> List[BaseTool]:
        """Return list of LangChain tools specific to this agent."""
        ...

    @abstractmethod
    def _assess_risk(self, user_input: str, response: str) -> Tuple[float, str]:
        """
        Return (risk_score 0..1, action_type) for HITL gating.
        0 = safe to auto-approve, 1 = definitely needs human.
        """
        ...

    # ── Prompt ────────────────────────────────────────────────────────────────
    def _build_prompt(self, context: str) -> ChatPromptTemplate:
        return ChatPromptTemplate.from_messages([
            (
                "system",
                f"{self.system_prompt}\n\n"
                "CONTEXT FROM COMPANY DOCUMENTS:\n{context}\n\n"
                "Always cite sources when using document context. "
                "If uncertain, say so clearly rather than guessing.",
            ),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

    # ── Core run ──────────────────────────────────────────────────────────────
    @log_agent_call.__wrapped__ if hasattr(log_agent_call, "__wrapped__") else lambda f: f
    async def run(
        self,
        user_input: str,
        session_id: str,
        extra_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        import time
        start = time.perf_counter()

        # 1. Load memory
        memory = get_agent_memory(session_id, self.agent_type)
        await memory.load()

        # 2. Retrieve RAG context
        rag_docs = await self.rag.retrieve(user_input, self.rag_scope, top_k=5)
        context_str = self._format_rag_context(rag_docs)
        if extra_context:
            context_str = f"{extra_context}\n\n{context_str}"

        # 3. Build and run agent executor
        prompt = self._build_prompt(context_str)
        agent = create_openai_tools_agent(self.llm, self._tools, prompt)
        executor = AgentExecutor(
            agent=agent,
            tools=self._tools,
            memory=memory.get_lc_memory(),
            max_iterations=settings.AGENT_MAX_ITERATIONS,
            verbose=settings.DEBUG,
            handle_parsing_errors=True,
            return_intermediate_steps=True,
        )

        try:
            result = await executor.ainvoke({
                "input": user_input,
                "context": context_str,
            })
        except Exception as exc:
            self.logger.error(f"Agent execution failed: {exc}", exc_info=True)
            metrics.record_call(self.agent_type, (time.perf_counter() - start) * 1000, False)
            raise

        response = result.get("output", "")
        intermediate_steps = result.get("intermediate_steps", [])

        # 4. Save turn to memory
        await memory.add_turn(user_input, response)

        # 5. HITL risk assessment
        risk_score, action_type = self._assess_risk(user_input, response)
        hitl_required = risk_score >= settings.HITL_HIGH_RISK_THRESHOLD

        elapsed = (time.perf_counter() - start) * 1000
        metrics.record_call(self.agent_type, elapsed, True)

        return {
            "response": response,
            "agent_type": self.agent_type,
            "sources": rag_docs,
            "intermediate_steps": [
                {"tool": step[0].tool, "input": step[0].tool_input, "output": str(step[1])}
                for step in intermediate_steps
            ],
            "hitl_required": hitl_required,
            "risk_score": risk_score,
            "action_type": action_type,
            "latency_ms": round(elapsed, 1),
        }

    # ── Helpers ───────────────────────────────────────────────────────────────
    @staticmethod
    def _format_rag_context(docs: List[Dict]) -> str:
        if not docs:
            return "No relevant company documents found."
        parts = []
        for i, doc in enumerate(docs, 1):
            parts.append(
                f"[Source {i}: {doc['source']} | score={doc['score']:.3f}]\n{doc['content']}"
            )
        return "\n\n---\n\n".join(parts)
