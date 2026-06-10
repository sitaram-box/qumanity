"use client";

import { useEffect, useState } from "react";
import { VerifiedBadge } from "@/components/ListingCard";
import type { Profile } from "@/lib/types";
import Link from "next/link";

export default function ProfilePage() {
  const [profile, setProfile] = useState<
    (Profile & { villages?: { name: string; state_name: string } }) | null
  >(null);

  useEffect(() => {
    fetch("/api/profile")
      .then((r) => r.json())
      .then((d) => setProfile(d.profile));
  }, []);

  if (!profile) {
    return (
      <div className="mx-auto max-w-lg px-4 py-12 text-center">
        <p className="text-soil/70">Please login to view your profile.</p>
        <Link href="/auth/login" className="btn-primary mt-4 inline-flex">
          Login
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-lg px-4 py-8">
      <div className="card text-center">
        <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-full bg-saffron/20 text-3xl font-bold text-saffron-dark">
          {profile.full_name.charAt(0) || "?"}
        </div>
        <h1 className="mt-4 text-2xl font-bold">{profile.full_name}</h1>
        {profile.is_verified && <VerifiedBadge className="mt-2" />}
        <p className="mt-2 text-sm text-soil/60">{profile.phone}</p>
        {profile.villages && (
          <p className="text-sm text-earth-green">
            {profile.villages.name}, {profile.villages.state_name}
          </p>
        )}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3">
        <div className="card text-center">
          <p className="text-2xl font-bold text-saffron-dark">{profile.trust_score}</p>
          <p className="text-xs text-soil/60">Trust Score</p>
        </div>
        <div className="card text-center">
          <p className="text-2xl font-bold text-earth-green">{profile.roles.length}</p>
          <p className="text-xs text-soil/60">Roles</p>
        </div>
      </div>

      {profile.trust_summary && (
        <div className="card mt-4">
          <p className="text-sm font-semibold">AI Trust Summary</p>
          <p className="mt-1 text-sm text-soil/70">{profile.trust_summary}</p>
        </div>
      )}

      <div className="card mt-4">
        <p className="text-sm font-semibold">Your Roles</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {profile.roles.map((r) => (
            <span key={r} className="rounded-full bg-wheat px-3 py-1 text-xs capitalize">
              {r.replace(/_/g, " ")}
            </span>
          ))}
        </div>
      </div>

      <div className="mt-4 space-y-2">
        <Link href="/register" className="btn-secondary block w-full text-center">
          Apply for New Role
        </Link>
        <Link href="/wallet" className="btn-primary block w-full text-center">
          View Qoins Wallet
        </Link>
      </div>

      <p className="mt-4 text-center text-xs text-soil/40">
        Aadhaar-ready structure · Future verification support
      </p>
    </div>
  );
}
