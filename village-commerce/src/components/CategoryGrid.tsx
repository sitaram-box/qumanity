"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { Category } from "@/lib/types";

const ICONS: Record<string, string> = {
  travel: "🛺",
  food: "🥬",
  labour: "👷",
  education: "📚",
  repair: "🔧",
  health: "💚",
  "women-services": "✨",
  delivery: "📦",
};

export function CategoryGrid({ kind }: { kind?: string }) {
  const [categories, setCategories] = useState<Category[]>([]);

  useEffect(() => {
    fetch("/api/categories")
      .then((r) => r.json())
      .then((d) => {
        let cats = d.categories ?? [];
        if (kind) cats = cats.filter((c: Category) => c.kind === kind && !c.parent_id);
        else cats = cats.filter((c: Category) => !c.parent_id);
        setCategories(cats);
      });
  }, [kind]);

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {categories.map((cat) => (
        <Link
          key={cat.id}
          href={`/marketplace?category=${cat.slug}`}
          className="card flex flex-col items-center gap-2 py-4 text-center transition hover:border-saffron hover:shadow-md"
        >
          <span className="text-3xl">{ICONS[cat.slug] ?? "📋"}</span>
          <span className="text-sm font-semibold">{cat.name_en}</span>
          {cat.name_hi && <span className="text-xs text-soil/60">{cat.name_hi}</span>}
        </Link>
      ))}
    </div>
  );
}
