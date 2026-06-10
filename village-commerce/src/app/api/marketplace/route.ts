import { NextResponse } from "next/server";
import { marketplaceSearch } from "@/lib/geo";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const results = await marketplaceSearch({
    query: searchParams.get("q") ?? undefined,
    categorySlug: searchParams.get("category") ?? undefined,
    villageId: searchParams.get("village_id") ?? undefined,
    lat: searchParams.get("lat") ? Number(searchParams.get("lat")) : undefined,
    lng: searchParams.get("lng") ? Number(searchParams.get("lng")) : undefined,
    type: (searchParams.get("type") as "service" | "product" | "employment" | "all") ?? "all",
    availableNow: searchParams.get("available_now") === "true",
    maxPrice: searchParams.get("max_price") ? Number(searchParams.get("max_price")) : undefined,
    minRating: searchParams.get("min_rating") ? Number(searchParams.get("min_rating")) : undefined,
    limit: searchParams.get("limit") ? Number(searchParams.get("limit")) : 20,
  });
  return NextResponse.json({ results });
}
