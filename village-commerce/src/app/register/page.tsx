"use client";

import { useState, useEffect } from "react";
import { VillageSearch } from "@/components/VillageSearch";
import type { Category } from "@/lib/types";
import { useRouter } from "next/navigation";

type RegType = "employment_seeker" | "service_provider" | "product_seller" | "delivery_agent";

const REG_OPTIONS: { type: RegType; label: string; labelHi: string }[] = [
  { type: "employment_seeker", label: "Looking for Employment", labelHi: "मैं रोजगार ढूंढ रहा/रही हूं" },
  { type: "service_provider", label: "Provide Services", labelHi: "मैं सेवाएं देना चाहता/चाहती हूं" },
  { type: "product_seller", label: "Sell Products", labelHi: "मैं सामान बेचना चाहता/चाहती हूं" },
  { type: "delivery_agent", label: "Become Delivery Agent", labelHi: "डिलीवरी एजेंट बनें" },
];

export default function RegisterPage() {
  const [regType, setRegType] = useState<RegType | null>(null);
  const [village, setVillage] = useState<{ id: string; name: string } | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const router = useRouter();

  const [form, setForm] = useState({
    category_id: "",
    subcategory_id: "",
    skills: "",
    expected_income: "",
    experience_years: "0",
    work_radius_km: "5",
    title: "",
    description: "",
    price_min: "",
    price_max: "",
    shop_name: "",
    vehicle_type: "bike",
    home_service: true,
    emergency_available: false,
    delivery_available: true,
    pickup_available: true,
  });

  useEffect(() => {
    fetch("/api/categories")
      .then((r) => r.json())
      .then((d) => setCategories(d.categories ?? []));
  }, []);

  const parentCategories = categories.filter((c) => !c.parent_id);
  const subcategories = categories.filter((c) => c.parent_id === form.category_id);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!regType || !village) {
      setMessage("Please select registration type and village");
      return;
    }

    setLoading(true);
    setMessage("");

    const payload: Record<string, unknown> = {
      category_id: form.category_id,
      subcategory_id: form.subcategory_id || null,
      experience_years: Number(form.experience_years),
    };

    if (regType === "employment_seeker") {
      Object.assign(payload, {
        skills: form.skills.split(",").map((s) => s.trim()).filter(Boolean),
        expected_income: Number(form.expected_income) || null,
        work_radius_km: Number(form.work_radius_km),
        availability: { weekdays: true, weekends: true },
      });
    } else if (regType === "service_provider") {
      Object.assign(payload, {
        title: form.title,
        description: form.description,
        price_min: Number(form.price_min) || null,
        price_max: Number(form.price_max) || null,
        home_service: form.home_service,
        emergency_available: form.emergency_available,
        service_area_km: Number(form.work_radius_km),
        working_hours: { start: "08:00", end: "18:00" },
      });
    } else if (regType === "product_seller") {
      Object.assign(payload, {
        shop_name: form.shop_name,
        description: form.description,
        pickup_available: form.pickup_available,
        delivery_available: form.delivery_available,
        products: [],
      });
    } else if (regType === "delivery_agent") {
      Object.assign(payload, {
        vehicle_type: form.vehicle_type,
        service_radius_km: Number(form.work_radius_km),
      });
    }

    const res = await fetch("/api/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        application_type: regType,
        village_id: village.id,
        payload,
      }),
    });

    const data = await res.json();
    setLoading(false);

    if (!res.ok) {
      setMessage(data.error ?? "Please login first");
      if (data.error?.includes("Unauthorized")) {
        router.push("/auth/login");
      }
      return;
    }

    setMessage("Application submitted! Village Council will verify soon. ✓");
  }

  return (
    <div className="mx-auto max-w-lg px-4 py-8">
      <h1 className="section-title mb-2">Register</h1>
      <p className="mb-6 text-soil/70">Verification Queue mein jayega · Council approve karega</p>

      {!regType ? (
        <div className="space-y-3">
          {REG_OPTIONS.map((opt) => (
            <button
              key={opt.type}
              type="button"
              className="card w-full text-left transition hover:border-saffron"
              onClick={() => setRegType(opt.type)}
            >
              <p className="font-bold">{opt.label}</p>
              <p className="text-sm text-soil/60">{opt.labelHi}</p>
            </button>
          ))}
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <button type="button" className="text-sm text-saffron-dark underline" onClick={() => setRegType(null)}>
            ← Change type
          </button>

          <div>
            <label className="mb-1 block text-sm font-medium">Village</label>
            <VillageSearch onSelect={setVillage} />
            {village && <p className="mt-1 text-xs text-earth-green">{village.name}</p>}
          </div>

          {regType !== "delivery_agent" && (
            <>
              <div>
                <label className="mb-1 block text-sm font-medium">Category</label>
                <select
                  className="input"
                  value={form.category_id}
                  onChange={(e) => setForm({ ...form, category_id: e.target.value, subcategory_id: "" })}
                  required
                >
                  <option value="">Select category</option>
                  {parentCategories.map((c) => (
                    <option key={c.id} value={c.id}>{c.name_en}</option>
                  ))}
                </select>
              </div>
              {subcategories.length > 0 && (
                <div>
                  <label className="mb-1 block text-sm font-medium">Subcategory</label>
                  <select
                    className="input"
                    value={form.subcategory_id}
                    onChange={(e) => setForm({ ...form, subcategory_id: e.target.value })}
                  >
                    <option value="">Select subcategory</option>
                    {subcategories.map((c) => (
                      <option key={c.id} value={c.id}>{c.name_en}</option>
                    ))}
                  </select>
                </div>
              )}
            </>
          )}

          {regType === "employment_seeker" && (
            <>
              <input className="input" placeholder="Skills (comma separated)" value={form.skills} onChange={(e) => setForm({ ...form, skills: e.target.value })} />
              <input className="input" type="number" placeholder="Expected daily income (₹)" value={form.expected_income} onChange={(e) => setForm({ ...form, expected_income: e.target.value })} />
              <input className="input" type="number" placeholder="Experience (years)" value={form.experience_years} onChange={(e) => setForm({ ...form, experience_years: e.target.value })} />
              <input className="input" type="number" placeholder="Work radius (km)" value={form.work_radius_km} onChange={(e) => setForm({ ...form, work_radius_km: e.target.value })} />
            </>
          )}

          {regType === "service_provider" && (
            <>
              <input className="input" placeholder="Service title (e.g. Plumber)" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required />
              <textarea className="input" placeholder="Description" rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
              <div className="grid grid-cols-2 gap-2">
                <input className="input" type="number" placeholder="Min price ₹" value={form.price_min} onChange={(e) => setForm({ ...form, price_min: e.target.value })} />
                <input className="input" type="number" placeholder="Max price ₹" value={form.price_max} onChange={(e) => setForm({ ...form, price_max: e.target.value })} />
              </div>
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={form.home_service} onChange={(e) => setForm({ ...form, home_service: e.target.checked })} />
                Home service available
              </label>
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={form.emergency_available} onChange={(e) => setForm({ ...form, emergency_available: e.target.checked })} />
                Emergency availability
              </label>
            </>
          )}

          {regType === "product_seller" && (
            <>
              <input className="input" placeholder="Shop name" value={form.shop_name} onChange={(e) => setForm({ ...form, shop_name: e.target.value })} required />
              <textarea className="input" placeholder="About your shop" rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={form.delivery_available} onChange={(e) => setForm({ ...form, delivery_available: e.target.checked })} />
                Delivery available
              </label>
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={form.pickup_available} onChange={(e) => setForm({ ...form, pickup_available: e.target.checked })} />
                Pickup available
              </label>
            </>
          )}

          {regType === "delivery_agent" && (
            <>
              <select className="input" value={form.vehicle_type} onChange={(e) => setForm({ ...form, vehicle_type: e.target.value })}>
                <option value="bike">Bike</option>
                <option value="auto">Auto</option>
                <option value="cycle">Cycle</option>
                <option value="foot">On Foot</option>
              </select>
              <input className="input" type="number" placeholder="Service radius (km)" value={form.work_radius_km} onChange={(e) => setForm({ ...form, work_radius_km: e.target.value })} />
            </>
          )}

          {message && (
            <p className={`text-sm ${message.includes("submitted") ? "text-earth-green" : "text-red-600"}`}>
              {message}
            </p>
          )}

          <button type="submit" className="btn-primary w-full" disabled={loading}>
            {loading ? "Submitting..." : "Submit for Verification"}
          </button>
        </form>
      )}
    </div>
  );
}
