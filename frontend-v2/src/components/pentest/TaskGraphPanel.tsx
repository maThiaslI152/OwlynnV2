import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";

interface TaskNode {
  id: string;
  type: string;
  category: string;
  description: string;
  tool: string;
  status: string;
  target: string;
  depends_on: string[];
  findings_count: number;
  priority: number;
}

interface TaskGraphData {
  engagement_id: string;
  nodes: Record<string, TaskNode>;
  edges: { from_id: string; to_id: string; condition: string }[];
  created_at: string;
  updated_at: string;
}

const STATUS_COLORS: Record<string, string> = {
  pending: "#6b7280",
  ready: "#3b82f6",
  running: "#f59e0b",
  complete: "#10b981",
  failed: "#ef4444",
  blocked: "#9ca3af",
  skipped: "#6b7280",
};

const CATEGORY_ICONS: Record<string, string> = {
  network: "🌐",
  web: "🕸️",
  vuln: "🔍",
  exploit: "💥",
  post_exploit: "🔓",
  osint: "🕵️",
  active_directory: "🏢",
  password: "🔑",
  cloud: "☁️",
  burp: "🔬",
};

export default function TaskGraphPanel({
  engagementId,
  activityCount,
}: {
  engagementId: string;
  activityCount: number;
}) {
  const [data, setData] = useState<TaskGraphData | null>(null);
  const [expanded, setExpanded] = useState(true);
  const [filter, setFilter] = useState<string>("all");

  const fetchGraph = useCallback(async () => {
    try {
      const resp = await fetch(`/api/pentest/engagements/${engagementId}/task-graph`);
      if (resp.ok) {
        const json = await resp.json();
        setData(json);
      }
    } catch { /* task graph fetch failed */ }
  }, [engagementId]);

  useEffect(() => {
    fetchGraph();
  }, [fetchGraph, activityCount]);

  if (!data || Object.keys(data.nodes).length === 0) return null;

  const nodes = Object.values(data.nodes);
  const statusCounts = nodes.reduce(
    (acc, n) => {
      acc[n.status] = (acc[n.status] || 0) + 1;
      return acc;
    },
    {} as Record<string, number>
  );
  const total = nodes.length;
  const done = (statusCounts.complete || 0) + (statusCounts.skipped || 0);
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;

  const filtered =
    filter === "all"
      ? nodes
      : nodes.filter((n) => n.status === filter);

  const sorted = [...filtered].sort((a, b) => {
    const order = { running: 0, ready: 1, pending: 2, blocked: 3, failed: 4, complete: 5, skipped: 6 };
    return (order[a.status as keyof typeof order] ?? 7) - (order[b.status as keyof typeof order] ?? 7);
  });

  return (
    <div className="glass-card" style={{ padding: 12 }}>
      <div
        style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}
        onClick={() => setExpanded(!expanded)}
      >
        <span style={{ fontWeight: 600, fontSize: 14 }}>
          Attack Task Graph
        </span>
        <span style={{ fontSize: 12, color: "#9ca3af" }}>
          {done}/{total} ({pct}%)
        </span>
        <div
          style={{
            flex: 1,
            height: 4,
            background: "#374151",
            borderRadius: 2,
            overflow: "hidden",
          }}
        >
          <motion.div
            style={{
              height: "100%",
              background: pct === 100 ? "#10b981" : "#3b82f6",
              borderRadius: 2,
            }}
            animate={{ width: `${pct}%` }}
            transition={{ duration: 0.5 }}
          />
        </div>
        <span style={{ fontSize: 12, color: "#6b7280" }}>
          {expanded ? "▲" : "▼"}
        </span>
      </div>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            style={{ overflow: "hidden" }}
          >
            <div
              style={{
                display: "flex",
                gap: 4,
                flexWrap: "wrap",
                marginTop: 8,
                marginBottom: 8,
              }}
            >
              {["all", ...Object.keys(statusCounts)].map((s) => (
                <button
                  key={s}
                  onClick={() => setFilter(s)}
                  style={{
                    padding: "2px 8px",
                    fontSize: 11,
                    borderRadius: 4,
                    border: filter === s ? "1px solid #3b82f6" : "1px solid #374151",
                    background: filter === s ? "#1e3a5f" : "transparent",
                    color: filter === s ? "#93c5fd" : "#9ca3af",
                    cursor: "pointer",
                  }}
                >
                  {s === "all" ? `All (${total})` : `${s} (${statusCounts[s] || 0})`}
                </button>
              ))}
            </div>

            <div style={{ maxHeight: 300, overflowY: "auto" }}>
              {sorted.map((node) => (
                <div
                  key={node.id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    padding: "4px 0",
                    borderBottom: "1px solid #1f2937",
                    fontSize: 12,
                  }}
                >
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: "50%",
                      background: STATUS_COLORS[node.status] || "#6b7280",
                      flexShrink: 0,
                    }}
                  />
                  <span style={{ width: 20, textAlign: "center" }}>
                    {CATEGORY_ICONS[node.category] || "🔧"}
                  </span>
                  <span
                    style={{
                      flex: 1,
                      color: node.status === "complete" ? "#6b7280" : "#e5e7eb",
                      textDecoration: node.status === "complete" ? "line-through" : "none",
                    }}
                  >
                    {node.description}
                  </span>
                  <span style={{ color: "#9ca3af", fontSize: 11 }}>{node.tool}</span>
                  {node.findings_count > 0 && (
                    <span
                      style={{
                        background: "#7c3aed",
                        color: "#fff",
                        padding: "1px 5px",
                        borderRadius: 3,
                        fontSize: 10,
                      }}
                    >
                      {node.findings_count}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
