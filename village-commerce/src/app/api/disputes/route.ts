import { NextResponse } from "next/server";
import { createClient, createServiceClient } from "@/lib/supabase/server";

export async function GET() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const service = await createServiceClient();
  const { data: profile } = await service
    .from("profiles")
    .select("roles")
    .eq("id", user.id)
    .single();

  const roles = profile?.roles ?? [];
  if (!roles.includes("village_council") && !roles.includes("super_admin")) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const { data } = await service
    .from("disputes")
    .select("*, orders(id, total_qoins), profiles!disputes_raised_by_fkey(full_name)")
    .order("created_at", { ascending: false });

  return NextResponse.json({ disputes: data ?? [] });
}

export async function POST(request: Request) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await request.json();
  const service = await createServiceClient();

  if (body.action === "resolve") {
    const { data: profile } = await service
      .from("profiles")
      .select("roles")
      .eq("id", user.id)
      .single();
    const roles = profile?.roles ?? [];
    if (!roles.includes("village_council") && !roles.includes("super_admin")) {
      return NextResponse.json({ error: "Forbidden" }, { status: 403 });
    }

    const { data, error } = await service
      .from("disputes")
      .update({
        status: "resolved",
        resolution: body.resolution,
        resolved_by: user.id,
        resolved_at: new Date().toISOString(),
      })
      .eq("id", body.dispute_id)
      .select()
      .single();
    if (error) return NextResponse.json({ error: error.message }, { status: 400 });
    return NextResponse.json({ dispute: data });
  }

  const { order_id, against_id, reason } = body;
  const { data, error } = await service
    .from("disputes")
    .insert({
      order_id,
      raised_by: user.id,
      against_id,
      reason,
      status: "open",
    })
    .select()
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 400 });

  await service.from("orders").update({ status: "disputed" }).eq("id", order_id);

  return NextResponse.json({ dispute: data });
}
