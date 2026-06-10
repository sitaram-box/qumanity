"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { ListingCard } from "@/components/ListingCard";
import { CategoryGrid } from "@/components/CategoryGrid";
import type { SearchResult } from "@/lib/types";
import { Search, Filter } from "lucide-react";

function MarketplaceContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [results, setResults] = useState<SearchResult[]>([]);
  const [query, setQuery] = useState(searchParams.get("q") ?? "");
  const [loading, setLoading] = useState(true);
  const [availableNow, setAvailableNow] = useState(false);
  const category = searchParams.get("category") ?? "";

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (category) params.set("category", category);
    if (availableNow) params.set("available_now", "true");
    params.set("type", "all");

    fetch(`/api/marketplace?${params}`)
      .then((r) => r.json())
      .then((d) => {
        setResults(d.results ?? []);
        setLoading(false);
      });
  }, [query, category, availableNow]);

  async function handleSelect(item: SearchResult) {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "create", participant_id: item.userId }),
    });
    const data = await res.json();
    if (data.chat) router.push(`/chat?id=${data.chat.id}`);
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <h1 className="section-title mb-2">Village Marketplace</h1>
      <p className="mb-6 text-soil/70">Services & Products · Verified providers · Qoins payment</p>

      <div className="mb-6 flex flex-col gap-3 sm:flex-row">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-soil/40" />
          <input
            className="input pl-10"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search plumber, vegetables, tuition..."
          />
        </div>
        <label className="flex items-center gap-2 rounded-xl border-2 border-wheat px-4 py-2">
          <Filter className="h-4 w-4" />
          <input type="checkbox" checked={availableNow} onChange={(e) => setAvailableNow(e.target.checked)} />
          Available Now
        </label>
      </div>

      {!category && (
        <div className="mb-8">
          <h2 className="mb-4 font-bold">Browse by Category</h2>
          <CategoryGrid />
        </div>
      )}

      {loading ? (
        <p className="text-center text-soil/50">Loading...</p>
      ) : results.length === 0 ? (
        <div className="card text-center py-12">
          <p className="text-soil/70">No listings yet. Register as a provider to get started.</p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {results.map((item) => (
            <ListingCard key={`${item.type}-${item.id}`} item={item} onSelect={handleSelect} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function MarketplacePage() {
  return (
    <Suspense fallback={<div className="p-8 text-center">Loading...</div>}>
      <MarketplaceContent />
    </Suspense>
  );
}
