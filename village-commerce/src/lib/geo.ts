import { createServiceClient } from "@/lib/supabase/server";
import { haversineKm, formatDistance } from "@/lib/utils";
import type { SearchResult } from "@/lib/types";

interface SearchParams {
  query?: string;
  categorySlug?: string;
  villageId?: string;
  lat?: number;
  lng?: number;
  maxPrice?: number;
  minRating?: number;
  availableNow?: boolean;
  type?: "service" | "product" | "employment" | "all";
  limit?: number;
}

export async function searchVillages(q: string, limit = 20) {
  const supabase = await createServiceClient();
  const { data, error } = await supabase
    .from("villages")
    .select("id, name, state_name, district_name, tehsil_name, latitude, longitude")
    .ilike("name", `%${q}%`)
    .limit(limit);
  if (error) throw new Error(error.message);
  return data ?? [];
}

export async function getVillageById(id: string) {
  const supabase = await createServiceClient();
  const { data } = await supabase
    .from("villages")
    .select("*")
    .eq("id", id)
    .single();
  return data;
}

export async function marketplaceSearch(params: SearchParams): Promise<SearchResult[]> {
  const supabase = await createServiceClient();
  const results: SearchResult[] = [];
  const limit = params.limit ?? 20;

  let villageLat = params.lat;
  let villageLng = params.lng;
  if (params.villageId && (villageLat == null || villageLng == null)) {
    const v = await getVillageById(params.villageId);
    if (v?.latitude && v?.longitude) {
      villageLat = v.latitude;
      villageLng = v.longitude;
    }
  }

  const categoryFilter = async () => {
    if (!params.categorySlug) return null;
    const { data } = await supabase
      .from("categories")
      .select("id")
      .eq("slug", params.categorySlug)
      .single();
    return data?.id ?? null;
  };

  const categoryId = await categoryFilter();

  if (params.type === "all" || params.type === "service" || !params.type) {
    let q = supabase
      .from("service_providers")
      .select(
        `*, profiles(id, full_name, is_verified, trust_score, village_id),
         categories:category_id(name_en, slug)`
      )
      .eq("is_active", true);

    if (categoryId) q = q.or(`category_id.eq.${categoryId},subcategory_id.eq.${categoryId}`);
    if (params.availableNow) q = q.eq("is_available_now", true);
    if (params.minRating) q = q.gte("avg_rating", params.minRating);
    if (params.maxPrice) q = q.lte("price_min", params.maxPrice);

    const { data: services } = await q.limit(limit);

    for (const s of services ?? []) {
      const profile = s.profiles as {
        full_name: string;
        is_verified: boolean;
        trust_score: number;
        village_id: string;
      } | null;

      let distance = "Nearby";
      if (villageLat != null && villageLng != null && params.villageId) {
        const v = await getVillageById(profile?.village_id ?? params.villageId);
        if (v?.latitude && v?.longitude) {
          distance = formatDistance(
            haversineKm(villageLat, villageLng, v.latitude, v.longitude)
          );
        }
      }

      if (params.query) {
        const ql = params.query.toLowerCase();
        const title = (s.title as string).toLowerCase();
        const cat = ((s.categories as { name_en?: string })?.name_en ?? "").toLowerCase();
        if (!title.includes(ql) && !cat.includes(ql)) continue;
      }

      results.push({
        id: s.id,
        type: "service",
        name: s.title,
        priceRange:
          s.price_min != null
            ? s.price_max != null && s.price_max !== s.price_min
              ? `₹${s.price_min}–₹${s.price_max}`
              : `₹${s.price_min}`
            : "Negotiable",
        rating: Number(s.avg_rating) || 0,
        distance,
        verified: profile?.is_verified ?? false,
        trustScore: profile?.trust_score ?? 0,
        deliveryAvailable: s.home_service ?? false,
        availableNow: s.is_available_now ?? false,
        userId: s.user_id,
      });
    }
  }

  if (params.type === "all" || params.type === "product" || !params.type) {
    let pq = supabase
      .from("products")
      .select(
        `*, product_sellers(*, profiles(id, full_name, is_verified, trust_score, village_id))`
      )
      .eq("is_available", true);

    if (categoryId) pq = pq.eq("category_id", categoryId);
    if (params.maxPrice) pq = pq.lte("price", params.maxPrice);

    const { data: products } = await pq.limit(limit);

    for (const p of products ?? []) {
      const seller = p.product_sellers as {
        delivery_available: boolean;
        profiles: { full_name: string; is_verified: boolean; trust_score: number };
      } | null;

      if (params.query) {
        const ql = params.query.toLowerCase();
        if (!(p.name as string).toLowerCase().includes(ql)) continue;
      }

      results.push({
        id: p.id,
        type: "product",
        name: p.name as string,
        priceRange: `₹${p.price}`,
        rating: Number((seller as { avg_rating?: number })?.avg_rating) || 0,
        distance: "Nearby",
        verified: seller?.profiles?.is_verified ?? false,
        trustScore: seller?.profiles?.trust_score ?? 0,
        deliveryAvailable: seller?.delivery_available ?? false,
        availableNow: true,
        userId: (seller as { user_id?: string })?.user_id ?? "",
      });
    }
  }

  if (params.type === "employment" || params.type === "all") {
    let eq = supabase
      .from("employment_seekers")
      .select(`*, profiles(id, full_name, is_verified, trust_score)`)
      .eq("is_active", true);

    if (categoryId) eq = eq.eq("category_id", categoryId);
    if (params.availableNow) eq = eq.eq("is_available_now", true);

    const { data: seekers } = await eq.limit(limit);

    for (const e of seekers ?? []) {
      const profile = e.profiles as {
        full_name: string;
        is_verified: boolean;
        trust_score: number;
      } | null;

      results.push({
        id: e.id,
        type: "employment",
        name: profile?.full_name ?? "Worker",
        priceRange: e.expected_income ? `₹${e.expected_income}/day` : "Negotiable",
        rating: 0,
        distance: "Nearby",
        verified: profile?.is_verified ?? false,
        trustScore: profile?.trust_score ?? 0,
        deliveryAvailable: false,
        availableNow: e.is_available_now ?? false,
        userId: e.user_id,
      });
    }
  }

  return results
    .sort((a, b) => {
      if (a.availableNow !== b.availableNow) return a.availableNow ? -1 : 1;
      if (a.verified !== b.verified) return a.verified ? -1 : 1;
      return b.rating - a.rating;
    })
    .slice(0, limit);
}

export async function findNearbyAgents(
  lat: number,
  lng: number,
  radiusKm = 10
) {
  const supabase = await createServiceClient();
  const { data } = await supabase
    .from("delivery_agents")
    .select("*, profiles(full_name, phone)")
    .eq("is_active", true)
    .eq("is_available", true);

  return (data ?? []).filter((a) => {
    if (a.current_lat == null || a.current_lng == null) return true;
    return haversineKm(lat, lng, a.current_lat, a.current_lng) <= radiusKm;
  });
}
