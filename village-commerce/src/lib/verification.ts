import { createServiceClient } from "@/lib/supabase/server";

export async function approveVerification(
  applicationId: string,
  reviewerId: string,
  notes?: string
) {
  const supabase = await createServiceClient();

  const { data: app, error } = await supabase
    .from("verification_applications")
    .update({
      status: "approved",
      reviewer_id: reviewerId,
      reviewer_notes: notes ?? null,
      reviewed_at: new Date().toISOString(),
    })
    .eq("id", applicationId)
    .select("*")
    .single();
  if (error) throw new Error(error.message);

  await supabase
    .from("profiles")
    .update({ is_verified: true, trust_score: 70 })
    .eq("id", app.user_id);

  const payload = app.payload as Record<string, unknown>;

  switch (app.application_type) {
    case "employment_seeker": {
      await supabase.from("employment_seekers").upsert({
        user_id: app.user_id,
        category_id: payload.category_id as string,
        subcategory_id: payload.subcategory_id as string,
        skills: (payload.skills as string[]) ?? [],
        expected_income: payload.expected_income as number,
        experience_years: (payload.experience_years as number) ?? 0,
        availability: payload.availability ?? {},
        work_radius_km: (payload.work_radius_km as number) ?? 5,
        verification_id: app.id,
        is_active: true,
      });
      await addRole(app.user_id, "employment_seeker");
      break;
    }
    case "service_provider": {
      await supabase.from("service_providers").upsert({
        user_id: app.user_id,
        category_id: payload.category_id as string,
        subcategory_id: payload.subcategory_id as string,
        title: (payload.title as string) ?? "Service Provider",
        description: payload.description as string,
        pricing_type: (payload.pricing_type as string) ?? "fixed",
        price_min: payload.price_min as number,
        price_max: payload.price_max as number,
        experience_years: (payload.experience_years as number) ?? 0,
        working_hours: payload.working_hours ?? {},
        service_area_km: (payload.service_area_km as number) ?? 5,
        home_service: payload.home_service ?? true,
        emergency_available: payload.emergency_available ?? false,
        verification_id: app.id,
        is_active: true,
      });
      await addRole(app.user_id, "service_provider");
      break;
    }
    case "product_seller": {
      const { data: seller } = await supabase
        .from("product_sellers")
        .upsert({
          user_id: app.user_id,
          shop_name: (payload.shop_name as string) ?? "Shop",
          category_id: payload.category_id as string,
          description: payload.description as string,
          pickup_available: payload.pickup_available ?? true,
          delivery_available: payload.delivery_available ?? true,
          verification_id: app.id,
          is_active: true,
        })
        .select("id")
        .single();

      if (seller && payload.products) {
        const products = payload.products as Array<Record<string, unknown>>;
        for (const p of products) {
          await supabase.from("products").insert({
            seller_id: seller.id,
            name: p.name as string,
            price: p.price as number,
            quantity: (p.quantity as number) ?? 1,
            category_id: payload.category_id as string,
            freshness_info: p.freshness_info as string,
            image_urls: (p.image_urls as string[]) ?? [],
          });
        }
      }
      await addRole(app.user_id, "product_seller");
      break;
    }
    case "delivery_agent": {
      await supabase.from("delivery_agents").upsert({
        user_id: app.user_id,
        vehicle_type: payload.vehicle_type as string,
        service_radius_km: (payload.service_radius_km as number) ?? 10,
        verification_id: app.id,
        is_active: true,
      });
      await addRole(app.user_id, "delivery_agent");
      break;
    }
  }

  return app;
}

export async function rejectVerification(
  applicationId: string,
  reviewerId: string,
  notes: string
) {
  const supabase = await createServiceClient();
  const { data, error } = await supabase
    .from("verification_applications")
    .update({
      status: "rejected",
      reviewer_id: reviewerId,
      reviewer_notes: notes,
      reviewed_at: new Date().toISOString(),
    })
    .eq("id", applicationId)
    .select("*")
    .single();
  if (error) throw new Error(error.message);
  return data;
}

async function addRole(userId: string, role: string) {
  const supabase = await createServiceClient();
  const { data: profile } = await supabase
    .from("profiles")
    .select("roles")
    .eq("id", userId)
    .single();
  const roles = profile?.roles ?? ["customer"];
  if (!roles.includes(role)) {
    await supabase
      .from("profiles")
      .update({ roles: [...roles, role] })
      .eq("id", userId);
  }
}

export async function getPendingVerifications(villageId?: string) {
  const supabase = await createServiceClient();
  let q = supabase
    .from("verification_applications")
    .select("*, profiles(full_name, phone, village_id)")
    .eq("status", "pending")
    .order("created_at", { ascending: true });
  if (villageId) q = q.eq("village_id", villageId);
  const { data } = await q;
  return data ?? [];
}

export async function getAdminAnalytics() {
  const supabase = await createServiceClient();

  const [
    { count: users },
    { count: providers },
    { count: sellers },
    { count: agents },
    { count: pending },
    { data: orders },
    { data: wallets },
  ] = await Promise.all([
    supabase.from("profiles").select("*", { count: "exact", head: true }),
    supabase.from("service_providers").select("*", { count: "exact", head: true }).eq("is_active", true),
    supabase.from("product_sellers").select("*", { count: "exact", head: true }).eq("is_active", true),
    supabase.from("delivery_agents").select("*", { count: "exact", head: true }).eq("is_active", true),
    supabase.from("verification_applications").select("*", { count: "exact", head: true }).eq("status", "pending"),
    supabase.from("orders").select("total_qoins, status, village_id").in("status", ["completed", "delivered"]),
    supabase.from("wallets").select("balance"),
  ]);

  const circulation = (wallets ?? []).reduce((s, w) => s + w.balance, 0);
  const totalSpent = (orders ?? []).reduce((s, o) => s + o.total_qoins, 0);

  const { data: topProviders } = await supabase
    .from("service_providers")
    .select("title, avg_rating, review_count, profiles(full_name)")
    .eq("is_active", true)
    .order("avg_rating", { ascending: false })
    .limit(5);

  const { data: reviews } = await supabase.from("reviews").select("rating_overall");
  const satisfaction =
    reviews && reviews.length > 0
      ? reviews.reduce((s, r) => s + r.rating_overall, 0) / reviews.length
      : 0;

  return {
    total_users: users ?? 0,
    active_providers: providers ?? 0,
    active_sellers: sellers ?? 0,
    active_agents: agents ?? 0,
    pending_verifications: pending ?? 0,
    qoins_circulation: circulation,
    total_spent: totalSpent,
    customer_satisfaction: satisfaction,
    top_providers: topProviders ?? [],
  };
}
