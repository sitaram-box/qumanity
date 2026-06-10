"use client";

import { useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { VillageSearch } from "@/components/VillageSearch";
import { Phone } from "lucide-react";

export default function LoginPage() {
  const [phone, setPhone] = useState("");
  const [otp, setOtp] = useState("");
  const [step, setStep] = useState<"phone" | "otp">("phone");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [village, setVillage] = useState<{ id: string; name: string } | null>(null);
  const [fullName, setFullName] = useState("");
  const router = useRouter();
  const supabase = createClient();

  async function sendOtp(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    const formatted = phone.startsWith("+") ? phone : `+91${phone.replace(/\D/g, "")}`;
    const { error: err } = await supabase.auth.signInWithOtp({ phone: formatted });
    setLoading(false);
    if (err) {
      setError(err.message);
      return;
    }
    setStep("otp");
  }

  async function verifyOtp(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    const formatted = phone.startsWith("+") ? phone : `+91${phone.replace(/\D/g, "")}`;
    const { data, error: err } = await supabase.auth.verifyOtp({
      phone: formatted,
      token: otp,
      type: "sms",
    });
    if (err) {
      setLoading(false);
      setError(err.message);
      return;
    }

    if (data.user && village && fullName) {
      await fetch("/api/profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          full_name: fullName,
          village_id: village.id,
          phone: formatted,
        }),
      });
    }

    setLoading(false);
    router.push("/marketplace");
    router.refresh();
  }

  return (
    <div className="mx-auto max-w-md px-4 py-12">
      <h1 className="section-title mb-2">Login / Register</h1>
      <p className="mb-6 text-soil/70">Mobile OTP se login karein · Gaanv select karein</p>

      {step === "phone" ? (
        <form onSubmit={sendOtp} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium">Mobile Number</label>
            <div className="relative">
              <Phone className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-soil/40" />
              <input
                className="input pl-10"
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="9876543210"
                required
              />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Full Name (new users)</label>
            <input
              className="input"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Your name"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Your Village</label>
            <VillageSearch
              onSelect={(v) => setVillage(v)}
              placeholder="Search village name..."
            />
            {village && <p className="mt-1 text-xs text-earth-green">Selected: {village.name}</p>}
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button type="submit" className="btn-primary w-full" disabled={loading}>
            {loading ? "Sending..." : "Send OTP"}
          </button>
        </form>
      ) : (
        <form onSubmit={verifyOtp} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium">Enter OTP</label>
            <input
              className="input text-center text-2xl tracking-widest"
              value={otp}
              onChange={(e) => setOtp(e.target.value)}
              placeholder="123456"
              maxLength={6}
              required
            />
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button type="submit" className="btn-primary w-full" disabled={loading}>
            {loading ? "Verifying..." : "Verify & Login"}
          </button>
          <button type="button" className="btn-secondary w-full" onClick={() => setStep("phone")}>
            Change Number
          </button>
        </form>
      )}

      <p className="mt-6 text-center text-sm text-soil/60">
        Aadhaar verification — coming soon ·{" "}
        <Link href="/register" className="text-saffron-dark underline">
          Register as Provider
        </Link>
      </p>
    </div>
  );
}
