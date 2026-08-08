import React, { useState, useMemo } from "react";
import {
  LayoutDashboard, MessageSquareWarning, Bot, ShieldAlert, Users, ScrollText,
  FileBarChart, Settings, Search, Bell, ChevronDown, CheckCircle2, AlertTriangle,
  Clock, Zap, Activity, TrendingUp, TrendingDown, Eye, Lock, Filter, MoreVertical,
  ArrowUpRight, ArrowDownRight, Cpu, Database, GitBranch, FileText, UserCog,
  KeyRound, Bell as BellIcon, Globe, ChevronRight, CircleDot
} from "lucide-react";
import {
  AreaChart, Area, LineChart, Line, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from "recharts";

// ---------- Mock Data ----------

const AGENTS = [
  { name: "Customer Agent", role: "Intake & triage", status: "active", load: 82, throughput: 412, avgLatency: 1.2, id: "AG-01" },
  { name: "Evidence Agent", role: "Document & image analysis", status: "active", load: 61, throughput: 298, avgLatency: 2.1, id: "AG-02" },
  { name: "Policy Agent", role: "RAG policy retrieval", status: "active", load: 74, throughput: 355, avgLatency: 0.9, id: "AG-03" },
  { name: "Fraud Agent", role: "Anomaly & risk scoring", status: "active", load: 45, throughput: 187, avgLatency: 1.7, id: "AG-04" },
  { name: "Resolution Agent", role: "Decision synthesis", status: "active", load: 68, throughput: 301, avgLatency: 1.4, id: "AG-05" },
  { name: "Workflow Agent", role: "Process orchestration", status: "active", load: 53, throughput: 402, avgLatency: 0.6, id: "AG-06" },
  { name: "Escalation Agent", role: "Human handoff routing", status: "idle", load: 12, throughput: 44, avgLatency: 0.8, id: "AG-07" },
  { name: "Learning Agent", role: "Feedback & fine-tuning", status: "active", load: 29, throughput: 96, avgLatency: 3.4, id: "AG-08" },
];

const COMPLAINTS = [
  { id: "CMP-10482", customer: "A. Nair", category: "Billing Dispute", status: "Resolved", agent: "Resolution Agent", confidence: 96, risk: "Low", updated: "4m ago" },
  { id: "CMP-10481", customer: "R. Menon", category: "Product Defect", status: "In Progress", agent: "Evidence Agent", confidence: 78, risk: "Low", updated: "9m ago" },
  { id: "CMP-10480", customer: "S. Iyer", category: "Warranty Claim", status: "Escalated", agent: "Escalation Agent", confidence: 41, risk: "High", updated: "12m ago" },
  { id: "CMP-10479", customer: "K. Pillai", category: "Refund Request", status: "Resolved", agent: "Resolution Agent", confidence: 91, risk: "Low", updated: "18m ago" },
  { id: "CMP-10478", customer: "T. Varma", category: "Fraud Flag", status: "Under Review", agent: "Fraud Agent", confidence: 63, risk: "High", updated: "22m ago" },
  { id: "CMP-10477", customer: "M. Devan", category: "SLA Breach", status: "In Progress", agent: "Workflow Agent", confidence: 84, risk: "Medium", updated: "31m ago" },
  { id: "CMP-10476", customer: "P. Krishnan", category: "Billing Dispute", status: "Resolved", agent: "Resolution Agent", confidence: 98, risk: "Low", updated: "44m ago" },
];

const VOLUME_TREND = [
  { day: "Mon", filed: 320, resolved: 289, autoResolved: 214 },
  { day: "Tue", filed: 298, resolved: 276, autoResolved: 201 },
  { day: "Wed", filed: 356, resolved: 312, autoResolved: 248 },
  { day: "Thu", filed: 401, resolved: 355, autoResolved: 279 },
  { day: "Fri", filed: 378, resolved: 340, autoResolved: 261 },
  { day: "Sat", filed: 214, resolved: 201, autoResolved: 168 },
  { day: "Sun", filed: 189, resolved: 179, autoResolved: 150 },
];

const AGENT_PERF = AGENTS.map(a => ({ name: a.name.replace(" Agent", ""), throughput: a.throughput }));

const RISK_DIST = [
  { name: "Low Risk", value: 68, color: "#2DD4BF" },
  { name: "Medium Risk", value: 21, color: "#F59E0B" },
  { name: "High Risk", value: 11, color: "#F43F5E" },
];

const USERS = [
  { name: "Ananya Nair", role: "Super Admin", email: "ananya@resolvix.ai", status: "Active", lastActive: "Now" },
  { name: "Rahul Menon", role: "Ops Manager", email: "rahul@resolvix.ai", status: "Active", lastActive: "2h ago" },
  { name: "Divya Iyer", role: "Fraud Analyst", email: "divya@resolvix.ai", status: "Active", lastActive: "1d ago" },
  { name: "Vishnu Pillai", role: "Support Lead", email: "vishnu@resolvix.ai", status: "Suspended", lastActive: "6d ago" },
];

const AUDIT_LOGS = [
  { time: "10:42:18", actor: "Resolution Agent", action: "Auto-resolved CMP-10482", detail: "Confidence 96% • Policy §4.2 applied" },
  { time: "10:39:02", actor: "Fraud Agent", action: "Flagged CMP-10478", detail: "Anomaly score 0.81 • duplicate invoice pattern" },
  { time: "10:31:55", actor: "R. Menon", action: "Overrode AI decision on CMP-10465", detail: "Manual approval, reason: goodwill gesture" },
  { time: "10:22:10", actor: "Policy Agent", action: "Retrieved 3 policy chunks", detail: "Warranty Policy §2.1, §2.3, FAQ #18" },
  { time: "10:15:47", actor: "System", action: "Learning Agent fine-tune cycle completed", detail: "412 new resolution samples ingested" },
];

const NAV = [
  { key: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { key: "complaints", label: "Complaints", icon: MessageSquareWarning },
  { key: "agents", label: "Agent Monitor", icon: Bot },
  { key: "fraud", label: "Fraud Analytics", icon: ShieldAlert },
  { key: "users", label: "User Management", icon: Users },
  { key: "audit", label: "Audit Logs", icon: ScrollText },
  { key: "reports", label: "Reports", icon: FileBarChart },
  { key: "settings", label: "Settings", icon: Settings },
];

// ---------- Small UI Primitives ----------

function StatusPill({ status }) {
  const map = {
    Resolved: { bg: "rgba(45,212,191,0.12)", fg: "#2DD4BF", dot: "#2DD4BF" },
    "In Progress": { bg: "rgba(96,165,250,0.12)", fg: "#60A5FA", dot: "#60A5FA" },
    Escalated: { bg: "rgba(244,63,94,0.12)", fg: "#F43F5E", dot: "#F43F5E" },
    "Under Review": { bg: "rgba(245,158,11,0.12)", fg: "#F59E0B", dot: "#F59E0B" },
    Active: { bg: "rgba(45,212,191,0.12)", fg: "#2DD4BF", dot: "#2DD4BF" },
    idle: { bg: "rgba(148,163,184,0.14)", fg: "#94A3B8", dot: "#94A3B8" },
    active: { bg: "rgba(45,212,191,0.12)", fg: "#2DD4BF", dot: "#2DD4BF" },
    Suspended: { bg: "rgba(244,63,94,0.12)", fg: "#F43F5E", dot: "#F43F5E" },
  };
  const s = map[status] || map["In Progress"];
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium"
      style={{ background: s.bg, color: s.fg }}
    >
      <CircleDot size={10} style={{ color: s.dot }} />
      {status}
    </span>
  );
}

function RiskPill({ risk }) {
  const map = { Low: "#2DD4BF", Medium: "#F59E0B", High: "#F43F5E" };
  return (
    <span className="text-xs font-mono font-semibold" style={{ color: map[risk] }}>
      {risk.toUpperCase()}
    </span>
  );
}

function Panel({ title, subtitle, action, children, className = "" }) {
  return (
    <div className={`rv-panel rounded-xl p-5 ${className}`}>
      {(title || action) && (
        <div className="flex items-start justify-between mb-4">
          <div>
            {title && <h3 className="text-sm font-semibold rv-text-primary tracking-wide">{title}</h3>}
            {subtitle && <p className="text-xs rv-text-dim mt-0.5">{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </div>
  );
}

function KpiCard({ label, value, delta, deltaPositive, icon: Icon, suffix = "" }) {
  return (
    <div className="rv-panel rounded-xl p-5 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-xs rv-text-dim uppercase tracking-wider font-medium">{label}</span>
        <div className="rv-icon-badge">
          <Icon size={15} />
        </div>
      </div>
      <div className="flex items-end justify-between">
        <span className="text-2xl font-semibold rv-text-primary font-mono">{value}{suffix}</span>
        {delta && (
          <span
            className="flex items-center gap-0.5 text-xs font-medium mb-1"
            style={{ color: deltaPositive ? "#2DD4BF" : "#F43F5E" }}
          >
            {deltaPositive ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}
            {delta}
          </span>
        )}
      </div>
    </div>
  );
}

// ---------- Sections ----------

function DashboardView() {
  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <KpiCard label="Complaints Filed (7d)" value="2,156" delta="8.4%" deltaPositive icon={MessageSquareWarning} />
        <KpiCard label="Auto-Resolved Rate" value="71.2" suffix="%" delta="3.1%" deltaPositive icon={Zap} />
        <KpiCard label="Avg Resolution Time" value="6.4" suffix="m" delta="1.2m" deltaPositive icon={Clock} />
        <KpiCard label="Fraud Caught" value="34" delta="2 new" icon={ShieldAlert} />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        <Panel title="Complaint Volume — Filed vs Resolved" subtitle="Last 7 days" className="xl:col-span-2">
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={VOLUME_TREND}>
              <defs>
                <linearGradient id="filedGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#60A5FA" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#60A5FA" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="autoGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#2DD4BF" stopOpacity={0.4} />
                  <stop offset="100%" stopColor="#2DD4BF" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1F2937" vertical={false} />
              <XAxis dataKey="day" stroke="#64748B" fontSize={12} tickLine={false} axisLine={false} />
              <YAxis stroke="#64748B" fontSize={12} tickLine={false} axisLine={false} />
              <Tooltip contentStyle={{ background: "#131826", border: "1px solid #1F2937", borderRadius: 8, fontSize: 12 }} />
              <Area type="monotone" dataKey="filed" stroke="#60A5FA" fill="url(#filedGrad)" strokeWidth={2} name="Filed" />
              <Area type="monotone" dataKey="autoResolved" stroke="#2DD4BF" fill="url(#autoGrad)" strokeWidth={2} name="Auto-Resolved" />
            </AreaChart>
          </ResponsiveContainer>
        </Panel>

        <Panel title="Risk Distribution" subtitle="Active complaint pool">
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie data={RISK_DIST} dataKey="value" innerRadius={55} outerRadius={80} paddingAngle={3}>
                {RISK_DIST.map((entry, i) => <Cell key={i} fill={entry.color} stroke="none" />)}
              </Pie>
              <Tooltip contentStyle={{ background: "#131826", border: "1px solid #1F2937", borderRadius: 8, fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex flex-col gap-2 mt-2">
            {RISK_DIST.map((r, i) => (
              <div key={i} className="flex items-center justify-between text-xs">
                <span className="flex items-center gap-2 rv-text-dim">
                  <span className="w-2 h-2 rounded-full" style={{ background: r.color }} />
                  {r.name}
                </span>
                <span className="font-mono rv-text-primary">{r.value}%</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <Panel title="Recent Activity" subtitle="Live agent decisions across the pipeline">
        <div className="flex flex-col divide-y rv-divide">
          {AUDIT_LOGS.slice(0, 4).map((log, i) => (
            <div key={i} className="flex items-center gap-4 py-3">
              <span className="text-xs font-mono rv-text-dim w-16 shrink-0">{log.time}</span>
              <span className="rv-icon-badge shrink-0"><Activity size={13} /></span>
              <div className="min-w-0">
                <p className="text-sm rv-text-primary truncate"><span className="font-medium">{log.actor}</span> — {log.action}</p>
                <p className="text-xs rv-text-dim truncate">{log.detail}</p>
              </div>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

function ComplaintsView() {
  const [filter, setFilter] = useState("All");
  const statuses = ["All", "In Progress", "Resolved", "Escalated", "Under Review"];
  const filtered = filter === "All" ? COMPLAINTS : COMPLAINTS.filter(c => c.status === filter);

  return (
    <div className="flex flex-col gap-5">
      <Panel
        title="Complaint Management"
        subtitle={`${filtered.length} complaints`}
        action={
          <div className="flex gap-2">
            {statuses.map(s => (
              <button
                key={s}
                onClick={() => setFilter(s)}
                className="text-xs px-3 py-1.5 rounded-lg font-medium transition-colors"
                style={{
                  background: filter === s ? "#2DD4BF" : "transparent",
                  color: filter === s ? "#0B0F19" : "#94A3B8",
                  border: filter === s ? "1px solid #2DD4BF" : "1px solid #1F2937",
                }}
              >
                {s}
              </button>
            ))}
          </div>
        }
      >
        <div className="overflow-x-auto -mx-1">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left rv-text-dim text-xs uppercase tracking-wider">
                <th className="font-medium px-3 py-2">ID</th>
                <th className="font-medium px-3 py-2">Customer</th>
                <th className="font-medium px-3 py-2">Category</th>
                <th className="font-medium px-3 py-2">Assigned Agent</th>
                <th className="font-medium px-3 py-2">Confidence</th>
                <th className="font-medium px-3 py-2">Risk</th>
                <th className="font-medium px-3 py-2">Status</th>
                <th className="font-medium px-3 py-2">Updated</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {filtered.map((c, i) => (
                <tr key={i} className="rv-row-hover" style={{ borderTop: "1px solid #1F2937" }}>
                  <td className="px-3 py-3 font-mono text-xs rv-text-primary">{c.id}</td>
                  <td className="px-3 py-3 rv-text-primary">{c.customer}</td>
                  <td className="px-3 py-3 rv-text-dim">{c.category}</td>
                  <td className="px-3 py-3 rv-text-dim">{c.agent}</td>
                  <td className="px-3 py-3">
                    <div className="flex items-center gap-2 w-20">
                      <div className="h-1.5 rounded-full rv-track flex-1">
                        <div className="h-1.5 rounded-full" style={{ width: `${c.confidence}%`, background: c.confidence > 70 ? "#2DD4BF" : "#F59E0B" }} />
                      </div>
                      <span className="text-xs font-mono rv-text-dim">{c.confidence}%</span>
                    </div>
                  </td>
                  <td className="px-3 py-3"><RiskPill risk={c.risk} /></td>
                  <td className="px-3 py-3"><StatusPill status={c.status} /></td>
                  <td className="px-3 py-3 text-xs rv-text-dim">{c.updated}</td>
                  <td className="px-3 py-3"><Eye size={15} className="rv-text-dim cursor-pointer" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}

function AgentMonitorView() {
  return (
    <div className="flex flex-col gap-5">
      <Panel title="Multi-Agent Pipeline" subtitle="8 autonomous agents · orchestrated via LangGraph">
        <div className="flex items-center gap-1 overflow-x-auto pb-2">
          {AGENTS.map((a, i) => (
            <React.Fragment key={a.id}>
              <div className="flex flex-col items-center gap-2 shrink-0" style={{ width: 108 }}>
                <div className="rv-agent-node" style={{ borderColor: a.status === "active" ? "#2DD4BF" : "#334155" }}>
                  <Bot size={18} style={{ color: a.status === "active" ? "#2DD4BF" : "#64748B" }} />
                  {a.status === "active" && <span className="rv-pulse-dot" />}
                </div>
                <span className="text-xs text-center rv-text-primary leading-tight">{a.name}</span>
                <span className="text-[10px] rv-text-dim font-mono">{a.load}% load</span>
              </div>
              {i < AGENTS.length - 1 && <ChevronRight size={14} className="rv-text-dim shrink-0 mb-6" />}
            </React.Fragment>
          ))}
        </div>
      </Panel>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        <Panel title="Throughput by Agent" subtitle="Requests processed today" className="xl:col-span-2">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={AGENT_PERF} layout="vertical" margin={{ left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1F2937" horizontal={false} />
              <XAxis type="number" stroke="#64748B" fontSize={11} tickLine={false} axisLine={false} />
              <YAxis type="category" dataKey="name" stroke="#94A3B8" fontSize={11} tickLine={false} axisLine={false} width={90} />
              <Tooltip contentStyle={{ background: "#131826", border: "1px solid #1F2937", borderRadius: 8, fontSize: 12 }} />
              <Bar dataKey="throughput" fill="#2DD4BF" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Panel>

        <Panel title="Agent Health">
          <div className="flex flex-col gap-3">
            {AGENTS.map((a, i) => (
              <div key={i} className="flex items-center justify-between">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="rv-icon-badge shrink-0"><Cpu size={12} /></span>
                  <span className="text-xs rv-text-primary truncate">{a.name}</span>
                </div>
                <StatusPill status={a.status} />
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <Panel title="Agent Detail" subtitle="Latency & responsibility per agent">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left rv-text-dim text-xs uppercase tracking-wider">
                <th className="font-medium px-3 py-2">Agent</th>
                <th className="font-medium px-3 py-2">Responsibility</th>
                <th className="font-medium px-3 py-2">Avg Latency</th>
                <th className="font-medium px-3 py-2">Throughput</th>
                <th className="font-medium px-3 py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {AGENTS.map((a, i) => (
                <tr key={i} style={{ borderTop: "1px solid #1F2937" }}>
                  <td className="px-3 py-3 rv-text-primary font-medium">{a.name}</td>
                  <td className="px-3 py-3 rv-text-dim">{a.role}</td>
                  <td className="px-3 py-3 font-mono text-xs rv-text-dim">{a.avgLatency}s</td>
                  <td className="px-3 py-3 font-mono text-xs rv-text-dim">{a.throughput}/day</td>
                  <td className="px-3 py-3"><StatusPill status={a.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}

function FraudAnalyticsView() {
  const flagged = COMPLAINTS.filter(c => c.risk !== "Low");
  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <KpiCard label="Flagged This Week" value="34" delta="2 new" icon={ShieldAlert} />
        <KpiCard label="False Positive Rate" value="4.1" suffix="%" delta="0.6%" deltaPositive icon={TrendingDown} />
        <KpiCard label="Avg Anomaly Score" value="0.62" icon={Activity} />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        <Panel title="Risk Distribution" className="xl:col-span-1">
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={RISK_DIST} dataKey="value" innerRadius={50} outerRadius={80} paddingAngle={3}>
                {RISK_DIST.map((entry, i) => <Cell key={i} fill={entry.color} stroke="none" />)}
              </Pie>
              <Tooltip contentStyle={{ background: "#131826", border: "1px solid #1F2937", borderRadius: 8, fontSize: 12 }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
            </PieChart>
          </ResponsiveContainer>
        </Panel>

        <Panel title="Flagged Complaints" subtitle="Requires analyst review" className="xl:col-span-2">
          <div className="flex flex-col divide-y rv-divide">
            {flagged.map((c, i) => (
              <div key={i} className="flex items-center justify-between py-3">
                <div className="flex items-center gap-3">
                  <span className="rv-icon-badge" style={{ background: "rgba(244,63,94,0.12)" }}>
                    <AlertTriangle size={13} style={{ color: "#F43F5E" }} />
                  </span>
                  <div>
                    <p className="text-sm rv-text-primary font-medium">{c.id} — {c.customer}</p>
                    <p className="text-xs rv-text-dim">{c.category}</p>
                  </div>
                </div>
                <RiskPill risk={c.risk} />
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <Panel title="Behavioral Signals" subtitle="Top anomaly contributors this week">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {[
            { label: "Duplicate Invoice Pattern", pct: 38 },
            { label: "Rapid Refiling Velocity", pct: 27 },
            { label: "Image Metadata Mismatch", pct: 19 },
          ].map((s, i) => (
            <div key={i} className="rv-panel-inset rounded-lg p-4">
              <p className="text-xs rv-text-dim mb-2">{s.label}</p>
              <div className="flex items-end gap-2">
                <span className="text-xl font-mono font-semibold rv-text-primary">{s.pct}%</span>
                <span className="text-xs rv-text-dim mb-1">of flags</span>
              </div>
              <div className="h-1.5 rounded-full rv-track mt-2">
                <div className="h-1.5 rounded-full" style={{ width: `${s.pct}%`, background: "#F43F5E" }} />
              </div>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

function UserManagementView() {
  return (
    <Panel
      title="User Management"
      subtitle={`${USERS.length} team members`}
      action={<button className="text-xs px-3 py-1.5 rounded-lg font-medium rv-btn-accent">+ Invite User</button>}
    >
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left rv-text-dim text-xs uppercase tracking-wider">
              <th className="font-medium px-3 py-2">Name</th>
              <th className="font-medium px-3 py-2">Role</th>
              <th className="font-medium px-3 py-2">Email</th>
              <th className="font-medium px-3 py-2">Status</th>
              <th className="font-medium px-3 py-2">Last Active</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {USERS.map((u, i) => (
              <tr key={i} style={{ borderTop: "1px solid #1F2937" }}>
                <td className="px-3 py-3 rv-text-primary font-medium flex items-center gap-2">
                  <span className="rv-avatar">{u.name.split(" ").map(n => n[0]).join("")}</span>
                  {u.name}
                </td>
                <td className="px-3 py-3 rv-text-dim">{u.role}</td>
                <td className="px-3 py-3 rv-text-dim font-mono text-xs">{u.email}</td>
                <td className="px-3 py-3"><StatusPill status={u.status} /></td>
                <td className="px-3 py-3 text-xs rv-text-dim">{u.lastActive}</td>
                <td className="px-3 py-3"><MoreVertical size={15} className="rv-text-dim cursor-pointer" /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function AuditLogsView() {
  return (
    <Panel title="Audit Logs" subtitle="Immutable record of every AI decision and human override">
      <div className="flex flex-col divide-y rv-divide">
        {AUDIT_LOGS.map((log, i) => (
          <div key={i} className="flex items-start gap-4 py-3.5">
            <span className="text-xs font-mono rv-text-dim w-16 shrink-0 mt-0.5">{log.time}</span>
            <span className="rv-icon-badge shrink-0"><ScrollText size={13} /></span>
            <div className="min-w-0 flex-1">
              <p className="text-sm rv-text-primary"><span className="font-semibold">{log.actor}</span> {log.action}</p>
              <p className="text-xs rv-text-dim mt-0.5">{log.detail}</p>
            </div>
            <Lock size={13} className="rv-text-dim shrink-0 mt-1" />
          </div>
        ))}
      </div>
    </Panel>
  );
}

function ReportsView() {
  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <KpiCard label="Cost Saved (Est.)" value="₹18.4L" delta="12%" deltaPositive icon={TrendingUp} />
        <KpiCard label="CSAT Score" value="4.6" suffix="/5" delta="0.2" deltaPositive icon={CheckCircle2} />
        <KpiCard label="SLA Compliance" value="94.2" suffix="%" delta="1.1%" deltaPositive icon={FileBarChart} />
      </div>
      <Panel title="Resolution Trend" subtitle="Filed vs resolved, 7-day rolling">
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={VOLUME_TREND}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1F2937" vertical={false} />
            <XAxis dataKey="day" stroke="#64748B" fontSize={12} tickLine={false} axisLine={false} />
            <YAxis stroke="#64748B" fontSize={12} tickLine={false} axisLine={false} />
            <Tooltip contentStyle={{ background: "#131826", border: "1px solid #1F2937", borderRadius: 8, fontSize: 12 }} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Line type="monotone" dataKey="filed" stroke="#60A5FA" strokeWidth={2} dot={false} name="Filed" />
            <Line type="monotone" dataKey="resolved" stroke="#2DD4BF" strokeWidth={2} dot={false} name="Resolved" />
          </LineChart>
        </ResponsiveContainer>
      </Panel>
      <Panel
        title="Exportable Reports"
        action={<button className="text-xs px-3 py-1.5 rounded-lg font-medium rv-btn-accent">Generate Report</button>}
      >
        <div className="flex flex-col divide-y rv-divide">
          {[
            { name: "Weekly Ops Summary", type: "PDF", updated: "Today, 09:00" },
            { name: "Fraud Detection Digest", type: "PDF", updated: "Yesterday" },
            { name: "Agent Performance Export", type: "CSV", updated: "3 days ago" },
          ].map((r, i) => (
            <div key={i} className="flex items-center justify-between py-3">
              <div className="flex items-center gap-3">
                <span className="rv-icon-badge"><FileText size={13} /></span>
                <div>
                  <p className="text-sm rv-text-primary">{r.name}</p>
                  <p className="text-xs rv-text-dim">{r.updated}</p>
                </div>
              </div>
              <span className="text-xs font-mono rv-text-dim">{r.type}</span>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

function SettingsView() {
  const groups = [
    { title: "Account", icon: UserCog, items: ["Organization profile", "Role & permissions (RBAC)", "Session management"] },
    { title: "Security", icon: KeyRound, items: ["Two-factor authentication", "API key rotation", "Encryption at rest — AES-256"] },
    { title: "Notifications", icon: BellIcon, items: ["Escalation alerts", "SLA breach warnings", "Weekly digest email"] },
    { title: "Integrations", icon: Globe, items: ["Vector database connection", "LLM provider & model routing", "Webhook endpoints"] },
  ];
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
      {groups.map((g, i) => (
        <Panel key={i} title={g.title} action={<span className="rv-icon-badge"><g.icon size={14} /></span>}>
          <div className="flex flex-col divide-y rv-divide">
            {g.items.map((item, j) => (
              <div key={j} className="flex items-center justify-between py-2.5 text-sm">
                <span className="rv-text-primary">{item}</span>
                <ChevronRight size={14} className="rv-text-dim" />
              </div>
            ))}
          </div>
        </Panel>
      ))}
    </div>
  );
}

// ---------- App Shell ----------

export default function AdminDashboard() {
  const [active, setActive] = useState("dashboard");
  const activeLabel = NAV.find(n => n.key === active)?.label;

  const view = useMemo(() => {
    switch (active) {
      case "dashboard": return <DashboardView />;
      case "complaints": return <ComplaintsView />;
      case "agents": return <AgentMonitorView />;
      case "fraud": return <FraudAnalyticsView />;
      case "users": return <UserManagementView />;
      case "audit": return <AuditLogsView />;
      case "reports": return <ReportsView />;
      case "settings": return <SettingsView />;
      default: return null;
    }
  }, [active]);

  return (
    <div className="rv-root" style={{ minHeight: "100vh", display: "flex" }}>
      <style>{`
        .rv-root {
          --bg: #0B0F19;
          --panel: #131826;
          --panel-inset: #0F1420;
          --border: #1F2937;
          --text-primary: #E2E8F0;
          --text-dim: #8B98AC;
          --accent: #2DD4BF;
          background: var(--bg);
          color: var(--text-primary);
          font-family: 'Inter', ui-sans-serif, system-ui, sans-serif;
        }
        .rv-display { font-family: 'Space Grotesk', 'Inter', sans-serif; }
        .rv-panel { background: var(--panel); border: 1px solid var(--border); }
        .rv-panel-inset { background: var(--panel-inset); border: 1px solid var(--border); }
        .rv-text-primary { color: var(--text-primary); }
        .rv-text-dim { color: var(--text-dim); }
        .rv-divide > * + * { border-top: 1px solid var(--border); }
        .rv-track { background: rgba(255,255,255,0.06); }
        .rv-icon-badge {
          display: inline-flex; align-items: center; justify-content: center;
          width: 28px; height: 28px; border-radius: 8px;
          background: rgba(45,212,191,0.10); color: var(--accent);
        }
        .rv-row-hover:hover { background: rgba(255,255,255,0.02); }
        .rv-btn-accent { background: var(--accent); color: #0B0F19; }
        .rv-avatar {
          width: 24px; height: 24px; border-radius: 999px; font-size: 10px;
          display: inline-flex; align-items: center; justify-content: center;
          background: rgba(96,165,250,0.15); color: #60A5FA; font-family: monospace;
        }
        .rv-agent-node {
          position: relative; width: 52px; height: 52px; border-radius: 14px;
          border: 1.5px solid; display: flex; align-items: center; justify-content: center;
          background: var(--panel-inset);
        }
        .rv-pulse-dot {
          position: absolute; top: -3px; right: -3px; width: 8px; height: 8px;
          border-radius: 999px; background: var(--accent);
          box-shadow: 0 0 0 rgba(45,212,191,0.5);
          animation: rv-pulse 2s infinite;
        }
        @keyframes rv-pulse {
          0% { box-shadow: 0 0 0 0 rgba(45,212,191,0.55); }
          70% { box-shadow: 0 0 0 7px rgba(45,212,191,0); }
          100% { box-shadow: 0 0 0 0 rgba(45,212,191,0); }
        }
        .rv-nav-item { color: var(--text-dim); transition: background 0.15s, color 0.15s; }
        .rv-nav-item:hover { background: rgba(255,255,255,0.04); color: var(--text-primary); }
        .rv-nav-item.active { background: rgba(45,212,191,0.10); color: var(--accent); }
        @media (prefers-reduced-motion: reduce) {
          .rv-pulse-dot { animation: none; }
        }
      `}</style>

      {/* Sidebar */}
      <aside style={{ width: 236, borderRight: "1px solid var(--border)" }} className="hidden md:flex flex-col shrink-0 py-5 px-3">
        <div className="flex items-center gap-2 px-2 mb-8">
          <div className="rv-icon-badge" style={{ width: 32, height: 32 }}>
            <GitBranch size={16} />
          </div>
          <div>
            <p className="rv-display text-sm font-bold tracking-tight rv-text-primary leading-none">RESOLVIX-AI</p>
            <p className="text-[10px] rv-text-dim tracking-wider mt-0.5">OPS CONSOLE</p>
          </div>
        </div>
        <nav className="flex flex-col gap-1">
          {NAV.map(n => (
            <button
              key={n.key}
              onClick={() => setActive(n.key)}
              className={`rv-nav-item flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-left ${active === n.key ? "active" : ""}`}
            >
              <n.icon size={16} />
              {n.label}
            </button>
          ))}
        </nav>
        <div className="mt-auto rv-panel-inset rounded-lg p-3 mx-1">
          <p className="text-xs rv-text-dim leading-relaxed">
            <span className="font-semibold" style={{ color: "var(--accent)" }}>8/8</span> agents online.
            System nominal.
          </p>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Topbar */}
        <header
          className="flex items-center justify-between gap-4 px-4 md:px-6 py-4 shrink-0"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <div>
            <h1 className="rv-display text-lg font-semibold rv-text-primary">{activeLabel}</h1>
            <p className="text-xs rv-text-dim">Resolvix-AI · Enterprise Complaint Resolution Platform</p>
          </div>
          <div className="flex items-center gap-3">
            <div className="hidden sm:flex items-center gap-2 rv-panel-inset rounded-lg px-3 py-2" style={{ width: 220 }}>
              <Search size={14} className="rv-text-dim" />
              <input
                placeholder="Search complaints, agents…"
                className="bg-transparent outline-none text-xs rv-text-primary placeholder:text-[#8B98AC] w-full"
              />
            </div>
            <button className="rv-icon-badge relative">
              <Bell size={15} />
              <span style={{ position: "absolute", top: -2, right: -2, width: 7, height: 7, borderRadius: 999, background: "#F43F5E" }} />
            </button>
            <div className="flex items-center gap-2 pl-2" style={{ borderLeft: "1px solid var(--border)" }}>
              <span className="rv-avatar">AN</span>
              <span className="hidden sm:inline text-xs rv-text-primary font-medium">Ananya N.</span>
              <ChevronDown size={13} className="rv-text-dim hidden sm:inline" />
            </div>
          </div>
        </header>

        {/* Mobile nav */}
        <div className="flex md:hidden overflow-x-auto gap-1 px-3 py-2" style={{ borderBottom: "1px solid var(--border)" }}>
          {NAV.map(n => (
            <button
              key={n.key}
              onClick={() => setActive(n.key)}
              className={`rv-nav-item flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium shrink-0 ${active === n.key ? "active" : ""}`}
            >
              <n.icon size={13} />
              {n.label}
            </button>
          ))}
        </div>

        <main className="flex-1 overflow-y-auto p-4 md:p-6">{view}</main>
      </div>
    </div>
  );
}
