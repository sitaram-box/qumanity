import { NextResponse } from "next/server";
import { createClient, createServiceClient } from "@/lib/supabase/server";

export async function POST(request: Request) {
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

  const body = await request.json();
  const { data, error } = await service
    .from("fraud_flags")
    .insert({
      user_id: body.user_id,
      flagged_by: user.id,
      reason: body.reason,
      severity: body.severity ?? "medium",
    })
    .select()
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json({ flag: data });
}

export async function GET() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const service = await createServiceClient();
  const { data } = await service
    .from("fraud_flags")
    .select("*, profiles!fraud_flags_user_id_fkey(full_name)")
    .eq("is_resolved", false)
    .order("created_at", { ascending: false });

  return NextResponse.json({ flags: data ?? [] });
}
