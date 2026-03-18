import { useState, useEffect, useRef } from "react";
import axios from "axios";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ── Auth helper ──────────────────────────────────────────────────────────────
const api = axios.create({ baseURL: API });
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// ── Agent badge colours ───────────────────────────────────────────────────────
const AGENT_COLOURS = {
  hr: { bg: "#e8f5e9", border: "#4caf50", text: "#1b5e20", label: "HR Agent" },
  finance: { bg: "#e3f2fd", border: "#2196f3", text: "#0d47a1", label: "Finance Agent" },
  support: { bg: "#fff3e0", border: "#ff9800", text: "#e65100", label: "Support Agent" },
  manager: { bg: "#f3e5f5", border: "#9c27b0", text: "#4a148c", label: "Manager Agent" },
};

const agentStyle = (type) => {
  const c = AGENT_COLOURS[type] || AGENT_COLOURS.manager;
  return {
    display: "inline-block",
    padding: "2px 10px",
    borderRadius: "12px",
    fontSize: "11px",
    fontWeight: 600,
    background: c.bg,
    border: `1px solid ${c.border}`,
    color: c.text,
    marginBottom: "6px",
  };
};

// ── Components ────────────────────────────────────────────────────────────────
function LoginPage({ onLogin }) {
  const [u, setU] = useState("employee@company.com");
  const [p, setP] = useState("password");
  const [err, setErr] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErr("");
    try {
      const form = new URLSearchParams();
      form.append("username", u);
      form.append("password", p);
      const { data } = await axios.post(`${API}/api/auth/token`, form);
      localStorage.setItem("access_token", data.access_token);
      onLogin(u);
    } catch {
      setErr("Login failed. Check credentials.");
    }
  };

  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh", background: "#f5f5f5" }}>
      <div style={{ background: "#fff", borderRadius: "16px", padding: "40px", width: "360px", boxShadow: "0 4px 24px rgba(0,0,0,0.08)" }}>
        <h1 style={{ margin: "0 0 4px", fontSize: "22px", fontWeight: 600 }}>Enterprise AI</h1>
        <p style={{ margin: "0 0 28px", color: "#666", fontSize: "14px" }}>Multi-Agent Assistant Platform</p>
        <form onSubmit={handleSubmit}>
          <label style={labelStyle}>Email</label>
          <input style={inputStyle} value={u} onChange={(e) => setU(e.target.value)} type="email" />
          <label style={labelStyle}>Password</label>
          <input style={inputStyle} value={p} onChange={(e) => setP(e.target.value)} type="password" />
          {err && <p style={{ color: "#c62828", fontSize: "13px", marginTop: "8px" }}>{err}</p>}
          <button style={btnPrimary} type="submit">Sign In</button>
        </form>
      </div>
    </div>
  );
}

function MetricsBar({ metrics }) {
  if (!metrics) return null;
  const agents = ["hr", "finance", "support", "manager"];
  return (
    <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
      {agents.map((a) => (
        <div key={a} style={{ background: "#fff", borderRadius: "10px", padding: "12px 16px", minWidth: "120px", border: "1px solid #eee" }}>
          <div style={{ fontSize: "11px", color: "#888", marginBottom: "4px" }}>{AGENT_COLOURS[a]?.label}</div>
          <div style={{ fontSize: "20px", fontWeight: 600 }}>{metrics.agent_calls?.[a] || 0}</div>
          <div style={{ fontSize: "11px", color: "#aaa" }}>{metrics.avg_latencies?.[a] ? `${metrics.avg_latencies[a]}ms avg` : "—"}</div>
        </div>
      ))}
      <div style={{ background: "#fff3e0", borderRadius: "10px", padding: "12px 16px", minWidth: "120px", border: "1px solid #ffe082" }}>
        <div style={{ fontSize: "11px", color: "#888", marginBottom: "4px" }}>HITL Events</div>
        <div style={{ fontSize: "20px", fontWeight: 600, color: "#e65100" }}>{metrics.hitl_events || 0}</div>
        <div style={{ fontSize: "11px", color: "#aaa" }}>needs review</div>
      </div>
    </div>
  );
}

function HITLBanner({ requestId, onApprove, onReject }) {
  return (
    <div style={{ background: "#fff8e1", border: "1px solid #ffca28", borderRadius: "10px", padding: "14px 16px", margin: "8px 0" }}>
      <div style={{ fontWeight: 600, color: "#f57f17", marginBottom: "6px" }}>⚠ Human Approval Required</div>
      <p style={{ margin: "0 0 10px", fontSize: "13px", color: "#555" }}>
        This action was flagged as high-risk and requires manager approval before proceeding.
      </p>
      <div style={{ display: "flex", gap: "8px" }}>
        <button onClick={() => onApprove(requestId)} style={{ ...btnSmall, background: "#e8f5e9", color: "#2e7d32", border: "1px solid #a5d6a7" }}>✓ Approve</button>
        <button onClick={() => onReject(requestId)} style={{ ...btnSmall, background: "#ffebee", color: "#c62828", border: "1px solid #ef9a9a" }}>✗ Reject</button>
      </div>
    </div>
  );
}

function ChatMessage({ msg }) {
  const isUser = msg.role === "user";
  return (
    <div style={{ display: "flex", justifyContent: isUser ? "flex-end" : "flex-start", marginBottom: "16px" }}>
      <div style={{
        maxWidth: "72%",
        background: isUser ? "#1a73e8" : "#fff",
        color: isUser ? "#fff" : "#222",
        borderRadius: isUser ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
        padding: "12px 16px",
        border: isUser ? "none" : "1px solid #eee",
        fontSize: "14px",
        lineHeight: "1.6",
      }}>
        {!isUser && msg.agentType && (
          <div style={agentStyle(msg.agentType)}>
            {AGENT_COLOURS[msg.agentType]?.label || msg.agentType}
          </div>
        )}
        <div style={{ whiteSpace: "pre-wrap" }}>{msg.content}</div>
        {msg.sources?.length > 0 && (
          <div style={{ marginTop: "8px", paddingTop: "8px", borderTop: "1px solid #eee", fontSize: "11px", color: "#888" }}>
            {msg.sources.map((s, i) => (
              <span key={i} style={{ marginRight: "8px" }}>📄 {s.source} ({s.score})</span>
            ))}
          </div>
        )}
        {msg.hitlRequestId && (
          <HITLBanner
            requestId={msg.hitlRequestId}
            onApprove={msg.onApprove}
            onReject={msg.onReject}
          />
        )}
      </div>
    </div>
  );
}

// ── Main App ─────────────────────────────────────────────────────────────────
export default function App() {
  const [userId, setUserId] = useState(localStorage.getItem("user_id") || "");
  const [messages, setMessages] = useState([
    { id: "0", role: "assistant", content: "Hello! I'm your Enterprise AI Assistant. I can help with HR, Finance, and IT Support questions. What can I help you with today?", agentType: "manager" },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [sidebarTab, setSidebarTab] = useState("chat");
  const [pendingHITL, setPendingHITL] = useState([]);
  const bottomRef = useRef(null);

  const handleLogin = (uid) => {
    setUserId(uid);
    localStorage.setItem("user_id", uid);
  };

  const handleLogout = () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("user_id");
    setUserId("");
  };

  useEffect(() => {
    if (!userId) return;
    const refresh = async () => {
      try {
        const { data } = await api.get("/api/metrics");
        setMetrics(data);
        const { data: hitl } = await api.get("/api/hitl/pending");
        setPendingHITL(hitl);
      } catch {}
    };
    refresh();
    const id = setInterval(refresh, 15000);
    return () => clearInterval(id);
  }, [userId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;
    const text = input.trim();
    setInput("");
    setMessages((m) => [...m, { id: Date.now().toString(), role: "user", content: text }]);
    setLoading(true);
    try {
      const { data } = await api.post("/api/chat", {
        user_id: userId,
        session_id: sessionId,
        message: text,
      });
      if (!sessionId) setSessionId(data.session_id);
      setMessages((m) => [...m, {
        id: Date.now().toString(),
        role: "assistant",
        content: data.response,
        agentType: data.agent_type,
        sources: data.sources,
        hitlRequestId: data.hitl_request_id,
        onApprove: (rid) => resolveHITL(rid, "approved"),
        onReject: (rid) => resolveHITL(rid, "rejected"),
      }]);
    } catch (err) {
      setMessages((m) => [...m, {
        id: Date.now().toString(),
        role: "assistant",
        content: `Error: ${err.response?.data?.detail || err.message}`,
        agentType: "manager",
      }]);
    } finally {
      setLoading(false);
    }
  };

  const resolveHITL = async (hitlId, decision) => {
    await api.post(`/api/hitl/${hitlId}/resolve`, {
      hitl_id: hitlId,
      decision,
      approver_id: userId,
      comment: `${decision} via dashboard`,
    });
    setMessages((m) => m.map((msg) =>
      msg.hitlRequestId === hitlId
        ? { ...msg, hitlRequestId: null, content: msg.content + `\n\n✓ Action ${decision}.` }
        : msg
    ));
  };

  if (!localStorage.getItem("access_token")) {
    return <LoginPage onLogin={handleLogin} />;
  }

  return (
    <div style={{ display: "flex", height: "100vh", fontFamily: "system-ui, sans-serif", background: "#f5f5f5" }}>
      {/* Sidebar */}
      <div style={{ width: "220px", background: "#1a1a2e", color: "#eee", display: "flex", flexDirection: "column", padding: "20px 16px" }}>
        <div style={{ fontWeight: 700, fontSize: "15px", marginBottom: "6px" }}>Enterprise AI</div>
        <div style={{ fontSize: "11px", color: "#888", marginBottom: "28px" }}>Multi-Agent Platform</div>
        {["chat", "approvals", "metrics"].map((tab) => (
          <button key={tab} onClick={() => setSidebarTab(tab)}
            style={{ background: sidebarTab === tab ? "#16213e" : "transparent", color: sidebarTab === tab ? "#4fc3f7" : "#aaa", border: "none", borderRadius: "8px", padding: "10px 12px", textAlign: "left", cursor: "pointer", marginBottom: "4px", fontSize: "13px", fontWeight: 500, display: "flex", alignItems: "center", gap: "8px" }}>
            {tab === "chat" ? "💬" : tab === "approvals" ? "⚠" : "📊"} {tab.charAt(0).toUpperCase() + tab.slice(1)}
            {tab === "approvals" && pendingHITL.length > 0 && (
              <span style={{ background: "#f57f17", color: "#fff", borderRadius: "10px", padding: "1px 7px", fontSize: "10px" }}>{pendingHITL.length}</span>
            )}
          </button>
        ))}
        <div style={{ marginTop: "auto" }}>
          <div style={{ fontSize: "11px", color: "#666", marginBottom: "8px" }}>{userId}</div>
          <button onClick={handleLogout} style={{ background: "transparent", color: "#888", border: "1px solid #333", borderRadius: "8px", padding: "6px 12px", cursor: "pointer", fontSize: "12px" }}>Sign Out</button>
        </div>
      </div>

      {/* Main content */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {/* Header */}
        <div style={{ background: "#fff", borderBottom: "1px solid #eee", padding: "16px 24px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <h2 style={{ margin: 0, fontSize: "17px", fontWeight: 600 }}>
            {sidebarTab === "chat" ? "AI Assistant" : sidebarTab === "approvals" ? "Pending Approvals" : "System Metrics"}
          </h2>
          <div style={{ display: "flex", gap: "8px" }}>
            {Object.entries(AGENT_COLOURS).map(([k, v]) => (
              <span key={k} style={{ fontSize: "11px", padding: "3px 8px", borderRadius: "10px", background: v.bg, color: v.text, border: `1px solid ${v.border}` }}>{v.label}</span>
            ))}
          </div>
        </div>

        {sidebarTab === "chat" && (
          <>
            <div style={{ flex: 1, overflowY: "auto", padding: "20px 24px" }}>
              {messages.map((m) => <ChatMessage key={m.id} msg={m} />)}
              {loading && (
                <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: "16px" }}>
                  <div style={{ background: "#fff", borderRadius: "18px", padding: "12px 18px", border: "1px solid #eee", color: "#888", fontSize: "14px" }}>
                    <span style={{ animation: "pulse 1s infinite" }}>●●●</span>
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>
            <div style={{ background: "#fff", borderTop: "1px solid #eee", padding: "16px 24px", display: "flex", gap: "12px" }}>
              <input
                style={{ flex: 1, border: "1px solid #ddd", borderRadius: "24px", padding: "10px 18px", fontSize: "14px", outline: "none" }}
                placeholder="Ask about HR, Finance, IT Support…"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSend()}
              />
              <button onClick={handleSend} disabled={loading || !input.trim()}
                style={{ ...btnPrimary, margin: 0, padding: "10px 22px", borderRadius: "24px", opacity: loading || !input.trim() ? 0.5 : 1 }}>
                Send
              </button>
            </div>
          </>
        )}

        {sidebarTab === "approvals" && (
          <div style={{ flex: 1, overflowY: "auto", padding: "24px" }}>
            {pendingHITL.length === 0 ? (
              <div style={{ textAlign: "center", color: "#aaa", marginTop: "60px" }}>No pending approvals</div>
            ) : pendingHITL.map((req) => (
              <div key={req.id} style={{ background: "#fff", borderRadius: "12px", padding: "20px", marginBottom: "16px", border: "1px solid #ffe082" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "10px" }}>
                  <div>
                    <span style={agentStyle(req.agent_type)}>{AGENT_COLOURS[req.agent_type]?.label}</span>
                    <div style={{ fontWeight: 600, marginTop: "4px" }}>{req.action_type}</div>
                    <div style={{ fontSize: "12px", color: "#888" }}>Session: {req.session_id}</div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: "13px", fontWeight: 600, color: req.risk_score > 0.8 ? "#c62828" : "#e65100" }}>
                      Risk: {Math.round(req.risk_score * 100)}%
                    </div>
                    <div style={{ fontSize: "11px", color: "#aaa" }}>{new Date(req.created_at).toLocaleTimeString()}</div>
                  </div>
                </div>
                <div style={{ background: "#f5f5f5", borderRadius: "8px", padding: "10px 12px", fontSize: "13px", marginBottom: "12px" }}>
                  <strong>Query:</strong> {req.payload?.user_input}
                </div>
                <div style={{ display: "flex", gap: "8px" }}>
                  <button onClick={() => resolveHITL(req.id, "approved")} style={{ ...btnSmall, background: "#e8f5e9", color: "#2e7d32", border: "1px solid #a5d6a7" }}>✓ Approve</button>
                  <button onClick={() => resolveHITL(req.id, "rejected")} style={{ ...btnSmall, background: "#ffebee", color: "#c62828", border: "1px solid #ef9a9a" }}>✗ Reject</button>
                </div>
              </div>
            ))}
          </div>
        )}

        {sidebarTab === "metrics" && (
          <div style={{ flex: 1, overflowY: "auto", padding: "24px" }}>
            <div style={{ marginBottom: "20px" }}>
              <MetricsBar metrics={metrics} />
            </div>
            {metrics && (
              <div style={{ background: "#fff", borderRadius: "12px", padding: "20px", border: "1px solid #eee" }}>
                <div style={{ fontWeight: 600, marginBottom: "14px" }}>Error Rates</div>
                {Object.keys(metrics.agent_calls || {}).map((agent) => {
                  const calls = metrics.agent_calls[agent] || 0;
                  const errors = metrics.errors?.[agent] || 0;
                  const rate = calls > 0 ? ((errors / calls) * 100).toFixed(1) : "0.0";
                  return (
                    <div key={agent} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid #f5f5f5", fontSize: "14px" }}>
                      <span style={agentStyle(agent)}>{AGENT_COLOURS[agent]?.label}</span>
                      <span>{calls} calls / {errors} errors ({rate}%)</span>
                    </div>
                  );
                })}
                <div style={{ marginTop: "14px", fontSize: "12px", color: "#aaa" }}>Uptime: {Math.round((metrics.uptime_seconds || 0) / 60)}m</div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────
const labelStyle = { display: "block", fontSize: "12px", fontWeight: 600, color: "#555", marginBottom: "4px" };
const inputStyle = { width: "100%", border: "1px solid #ddd", borderRadius: "8px", padding: "9px 12px", fontSize: "14px", marginBottom: "14px", boxSizing: "border-box" };
const btnPrimary = { display: "block", width: "100%", background: "#1a73e8", color: "#fff", border: "none", borderRadius: "8px", padding: "11px", fontSize: "14px", fontWeight: 600, cursor: "pointer", marginTop: "4px" };
const btnSmall = { padding: "6px 14px", borderRadius: "8px", cursor: "pointer", fontSize: "13px", fontWeight: 500 };
