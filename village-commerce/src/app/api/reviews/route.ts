import { NextResponse } from "next/server";
import { createClient, createServiceClient } from "@/lib/supabase/server";
import { generateTrustSummary } from "@/lib/ai";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const revieweeId = searchParams.get("reviewee_id");

  const supabase = await createClient();
  let q = supabase.from("reviews").select("*, profiles!reviews_reviewer_id_fkey(full_name)").order("created_at", { ascending: false });
  if (revieweeId) q = q.eq("reviewee_id", revieweeId);

  const { data } = await q.limit(50);
  return NextResponse.json({ reviews: data ?? [] });
}

export async function POST(request: Request) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await request.json();
  const service = await createServiceClient();

  const { data: review, error } = await service
    .from("reviews")
    .insert({ ...body, reviewer_id: user.id })
    .select()
    .single();
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });

  const { data: allReviews } = await service
    .from("reviews")
    .select("rating_overall, comment")
    .eq("reviewee_id", body.reviewee_id);

  const avg =
    (allReviews ?? []).reduce((s, r) => s + r.rating_overall, 0) /
    (allReviews?.length ?? 1);

  const summary = await generateTrustSummary(allReviews ?? []);

  await service
    .from("profiles")
    .update({ trust_summary: summary, trust_score: Math.min(100, Math.round(avg * 18)) })
    .eq("id", body.reviewee_id);

  if (body.review_type === "service_provider") {
    await service
      .from("service_providers")
      .update({ avg_rating: avg, review_count: allReviews?.length ?? 0 })
      .eq("user_id", body.reviewee_id);
  }

  return NextResponse.json({ review });
}
