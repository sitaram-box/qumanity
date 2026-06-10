"use client";

import { useState, useEffect } from "react";
import { Search } from "lucide-react";

interface Village {
  id: string;
  name: string;
  state_name: string | null;
  district_name: string | null;
}

interface VillageSearchProps {
  onSelect: (village: Village) => void;
  placeholder?: string;
}

export function VillageSearch({ onSelect, placeholder = "Search your village..." }: VillageSearchProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Village[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (query.length < 2) {
      setResults([]);
      return;
    }
    const t = setTimeout(async () => {
      setLoading(true);
      const res = await fetch(`/api/villages?q=${encodeURIComponent(query)}`);
      const data = await res.json();
      setResults(data.villages ?? []);
      setLoading(false);
    }, 300);
    return () => clearTimeout(t);
  }, [query]);

  return (
    <div className="relative">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-soil/40" />
        <input
          className="input pl-10"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={placeholder}
          aria-label="Search village"
        />
      </div>
      {loading && <p className="mt-1 text-xs text-soil/50">Searching...</p>}
      {results.length > 0 && (
        <ul className="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-xl border border-wheat bg-white shadow-lg">
          {results.map((v) => (
            <li key={v.id}>
              <button
                type="button"
                className="w-full px-4 py-3 text-left hover:bg-wheat/50"
                onClick={() => {
                  onSelect(v);
                  setQuery(v.name);
                  setResults([]);
                }}
              >
                <p className="font-medium">{v.name}</p>
                <p className="text-xs text-soil/60">
                  {[v.district_name, v.state_name].filter(Boolean).join(", ")}
                </p>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
