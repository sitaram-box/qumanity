"use client";

import { useEffect, useState } from "react";
import { ListingCard } from "@/components/ListingCard";
import type { SearchResult } from "@/lib/types";

export default function ProductsPage() {
  const [results, setResults] = useState<SearchResult[]>([]);

  useEffect(() => {
    fetch("/api/marketplace?type=product")
      .then((r) => r.json())
      .then((d) => setResults(d.results ?? []));
  }, []);

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <h1 className="section-title mb-6">Product Marketplace</h1>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {results.map((item) => (
          <ListingCard key={item.id} item={item} />
        ))}
      </div>
    </div>
  );
}
