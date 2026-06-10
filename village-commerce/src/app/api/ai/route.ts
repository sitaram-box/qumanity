import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { processAIQuery } from "@/lib/ai";

export async function POST(request: Request) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();

  const body = await request.json();
  const { message, village_id, lat, lng } = body;

  if (!message) {
    return NextResponse.json({ error: "Message required" }, { status: 400 });
  }

  let vId = village_id;
  if (!vId && user) {
    const { data: profile } = await supabase
      .from("profiles")
      .select("village_id")
      .eq("id", user.id)
      .single();
    vId = profile?.village_id;
  }

  const result = await processAIQuery(message, vId, lat, lng);
  return NextResponse.json(result);
}
