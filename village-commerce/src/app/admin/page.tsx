"use client";

import { useEffect, useState } from "react";
import { Shield, TrendingUp, Users, AlertTriangle, BadgeCheck } from "lucide-react";

interface PendingApp {
  id: string;
  application_type: string;
  status: string;
  payload: Record<string, unknown>;
  created_at: string;
  profiles: { full_name: string; phone: string | null };
}

interface Analytics {
  total_users: number;
  active_providers: number;
  active_sellers: number;
  active_agents: number;
  pending_verifications: number;
  qoins_circulation: number;
  total_spent: number;
  customer_satisfaction: number;
  top_providers: Array<{ title: string; avg_rating: number; profiles: { full_name: string } }>;
}

export default function AdminPage() {
  const [pending, setPending] = useState<PendingApp[]>([]);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [tab, setTab] = useState<"verify" | "analytics">("verify");
  const [notes, setNotes] = useState<Record<string, string>>({});

  function load() {
    fetch("/api/admin")
      .then((r) => r.json())
      .then((d) => setPending(d.pending ?? []));
    fetch("/api/admin?view=analytics")
      .then((r) => r.json())
      .then((d) => setAnalytics(d.analytics));
  }

  useEffect(() => {
    load();
  }, []);

  async function review(id: string, action: "approve" | "reject") {
    await fetch("/api/admin", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, application_id: id, notes: notes[id] }),
    });
    load();
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <div className="mb-6 flex items-center gap-3">
        <Shield className="h-8 w-8 text-saffron" />
        <div>
          <h1 className="section-title !text-2xl">Village Council Dashboard</h1>
          <p className="text-sm text-soil/60">Quantum Punch Verification Team</p>
        </div>
      </div>

      <div className="mb-6 flex gap-2">
        <button
          type="button"
          className={`rounded-xl px-4 py-2 text-sm font-medium ${tab === "verify" ? "bg-saffron text-white" : "bg-wheat/50"}`}
          onClick={() => setTab("verify")}
        >
          Verifications ({pending.length})
        </button>
        <button
          type="button"
          className={`rounded-xl px-4 py-2 text-sm font-medium ${tab === "analytics" ? "bg-saffron text-white" : "bg-wheat/50"}`}
          onClick={() => setTab("analytics")}
        >
          Analytics
        </button>
      </div>

      {tab === "verify" && (
        <div className="space-y-4">
          {pending.length === 0 ? (
            <div className="card py-12 text-center text-soil/60">No pending verifications ✓</div>
          ) : (
            pending.map((app) => (
              <article key={app.id} className="card">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="font-bold">{app.profiles?.full_name}</p>
                    <p className="text-sm capitalize text-soil/60">
                      {app.application_type.replace(/_/g, " ")}
                    </p>
                    <p className="text-xs text-soil/40">
                      {new Date(app.created_at).toLocaleString("en-IN")}
                    </p>
                  </div>
                  <span className="rounded-full bg-yellow-100 px-2 py-1 text-xs font-semibold text-yellow-800">
                    Pending
                  </span>
                </div>
                <pre className="mt-3 max-h-32 overflow-auto rounded-lg bg-wheat/30 p-2 text-xs">
                  {JSON.stringify(app.payload, null, 2)}
                </pre>
                <textarea
                  className="input mt-3 !py-2 text-sm"
                  placeholder="Reviewer notes..."
                  value={notes[app.id] ?? ""}
                  onChange={(e) => setNotes({ ...notes, [app.id]: e.target.value })}
                />
                <div className="mt-3 flex gap-2">
                  <button
                    type="button"
                    className="btn-primary !py-2 !text-sm"
                    onClick={() => review(app.id, "approve")}
                  >
                    Approve · Verified Badge + Trust 70
                  </button>
                  <button
                    type="button"
                    className="rounded-xl border-2 border-red-300 px-4 py-2 text-sm font-semibold text-red-600"
                    onClick={() => review(app.id, "reject")}
                  >
                    Reject
                  </button>
                </div>
              </article>
            ))
          )}
        </div>
      )}

      {tab === "analytics" && analytics && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {[
              { icon: Users, label: "Users", value: analytics.total_users },
              { icon: BadgeCheck, label: "Providers", value: analytics.active_providers },
              { icon: TrendingUp, label: "Qoins Circulation", value: analytics.qoins_circulation },
              { icon: AlertTriangle, label: "Pending", value: analytics.pending_verifications },
            ].map(({ icon: Icon, label, value }) => (
              <div key={label} className="card text-center">
                <Icon className="mx-auto mb-1 h-5 w-5 text-saffron" />
                <p className="text-2xl font-bold text-saffron-dark">{value}</p>
                <p className="text-xs text-soil/60">{label}</p>
              </div>
            ))}
          </div>
          <div className="card">
            <h3 className="font-bold">Village Economy</h3>
            <p className="mt-2 text-sm">Total Qoins spent: {analytics.total_spent}</p>
            <p className="text-sm">Customer satisfaction: {analytics.customer_satisfaction.toFixed(1)}★</p>
            <p className="text-sm">Active sellers: {analytics.active_sellers} · Agents: {analytics.active_agents}</p>
          </div>
          {analytics.top_providers.length > 0 && (
            <div className="card">
              <h3 className="mb-3 font-bold">Top Providers</h3>
              <ul className="space-y-2">
                {analytics.top_providers.map((p, i) => (
                  <li key={i} className="flex justify-between text-sm">
                    <span>{p.title} — {p.profiles?.full_name}</span>
                    <span>{Number(p.avg_rating).toFixed(1)}★</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
