import { NextResponse } from "next/server";
import { createClient, createServiceClient } from "@/lib/supabase/server";

export async function POST(request: Request) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await request.json();
  const { application_type, village_id, payload, documents } = body;

  if (!application_type || !village_id || !payload) {
    return NextResponse.json({ error: "Missing required fields" }, { status: 400 });
  }

  const service = await createServiceClient();
  const { data, error } = await service
    .from("verification_applications")
    .insert({
      user_id: user.id,
      application_type,
      village_id,
      payload,
      documents: documents ?? [],
      status: "pending",
    })
    .select()
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json({ application: data });
}

export async function GET() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { data } = await supabase
    .from("verification_applications")
    .select("*")
    .eq("user_id", user.id)
    .order("created_at", { ascending: false });

  return NextResponse.json({ applications: data ?? [] });
}
