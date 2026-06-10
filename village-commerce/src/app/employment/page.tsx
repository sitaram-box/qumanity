"use client";

import { useEffect, useState } from "react";
import { ListingCard } from "@/components/ListingCard";
import type { SearchResult } from "@/lib/types";

export default function EmploymentPage() {
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/marketplace?type=employment")
      .then((r) => r.json())
      .then((d) => {
        setResults(d.results ?? []);
        setLoading(false);
      });
  }, []);

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <h1 className="section-title mb-2">Employment Exchange</h1>
      <p className="mb-6 text-soil/70">
        Verified labourers & skilled workers · रोजगार खोजें
      </p>

      {loading ? (
        <p className="text-center text-soil/50">Loading...</p>
      ) : results.length === 0 ? (
        <div className="card py-12 text-center">
          <p className="text-soil/70">No verified workers yet in your area.</p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {results.map((item) => (
            <ListingCard key={item.id} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}
