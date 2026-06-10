"use client";

import { useEffect, useState } from "react";
import { Truck, Package, MapPin, CheckCircle } from "lucide-react";

interface DeliveryTask {
  id: string;
  status: string;
  estimated_minutes: number | null;
  distance_km: number | null;
  orders: {
    id: string;
    delivery_address: string | null;
    total_qoins: number;
    otp_code?: string;
  };
}

const STATUS_LABELS: Record<string, string> = {
  notified: "Available — Accept Now",
  accepted: "Accepted",
  picked_up: "Picked Up",
  en_route: "En Route",
  delivered: "Delivered",
};

export default function DeliveryPage() {
  const [tasks, setTasks] = useState<DeliveryTask[]>([]);
  const [loading, setLoading] = useState(true);

  function loadTasks() {
    fetch("/api/delivery")
      .then((r) => r.json())
      .then((d) => {
        setTasks(d.tasks ?? []);
        setLoading(false);
      });
  }

  useEffect(() => {
    loadTasks();
    const interval = setInterval(loadTasks, 10000);
    return () => clearInterval(interval);
  }, []);

  async function acceptTask(taskId: string) {
    await fetch("/api/delivery", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "accept", task_id: taskId }),
    });
    loadTasks();
  }

  async function updateStatus(taskId: string, status: "picked_up" | "en_route" | "delivered") {
    await fetch("/api/delivery", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "update_status", task_id: taskId, status }),
    });
    loadTasks();
  }

  return (
    <div className="mx-auto max-w-lg px-4 py-8">
      <h1 className="section-title mb-2">Delivery Dashboard</h1>
      <p className="mb-6 text-soil/70">Accept tasks · Update status · Earn Qoins</p>

      {loading ? (
        <p>Loading...</p>
      ) : tasks.length === 0 ? (
        <div className="card py-12 text-center">
          <Truck className="mx-auto h-12 w-12 text-soil/30" />
          <p className="mt-3 text-soil/70">No delivery tasks right now</p>
        </div>
      ) : (
        <div className="space-y-4">
          {tasks.map((task) => (
            <article key={task.id} className="card">
              <div className="flex items-center justify-between">
                <span className="badge-available">{STATUS_LABELS[task.status] ?? task.status}</span>
                {task.estimated_minutes && (
                  <span className="text-xs text-soil/60">~{task.estimated_minutes} min</span>
                )}
              </div>
              <p className="mt-2 flex items-start gap-2 text-sm">
                <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-saffron" />
                {task.orders?.delivery_address ?? "Village delivery"}
              </p>
              <p className="mt-1 text-sm font-semibold text-saffron-dark">
                {task.orders?.total_qoins ?? 0} Qoins
              </p>

              <div className="mt-3 flex flex-wrap gap-2">
                {task.status === "notified" && (
                  <button type="button" className="btn-primary !py-2 !text-sm" onClick={() => acceptTask(task.id)}>
                    Accept Delivery
                  </button>
                )}
                {task.status === "accepted" && (
                  <button type="button" className="btn-secondary !py-2 !text-sm" onClick={() => updateStatus(task.id, "picked_up")}>
                    <Package className="h-4 w-4" /> Picked Up
                  </button>
                )}
                {task.status === "picked_up" && (
                  <button type="button" className="btn-secondary !py-2 !text-sm" onClick={() => updateStatus(task.id, "en_route")}>
                    En Route
                  </button>
                )}
                {task.status === "en_route" && (
                  <button type="button" className="btn-primary !py-2 !text-sm" onClick={() => updateStatus(task.id, "delivered")}>
                    <CheckCircle className="h-4 w-4" /> Mark Delivered
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
