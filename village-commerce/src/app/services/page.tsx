"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { ListingCard } from "@/components/ListingCard";
import type { SearchResult } from "@/lib/types";

function ServicesContent() {
  const searchParams = useSearchParams();
  const category = searchParams.get("category") ?? "";
  const [results, setResults] = useState<SearchResult[]>([]);

  useEffect(() => {
    const params = new URLSearchParams({ type: "service" });
    if (category) params.set("category", category);
    fetch(`/api/marketplace?${params}`)
      .then((r) => r.json())
      .then((d) => setResults(d.results ?? []));
  }, [category]);

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <h1 className="section-title mb-6">Service Providers</h1>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {results.map((item) => (
          <ListingCard key={item.id} item={item} />
        ))}
      </div>
    </div>
  );
}

export default function ServicesPage() {
  return (
    <Suspense fallback={<div className="p-8">Loading...</div>}>
      <ServicesContent />
    </Suspense>
  );
}
