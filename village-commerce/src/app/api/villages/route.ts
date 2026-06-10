import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { searchVillages } from "@/lib/geo";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const q = searchParams.get("q") ?? "";
  if (q.length < 2) {
    return NextResponse.json({ villages: [] });
  }
  const villages = await searchVillages(q);
  return NextResponse.json({ villages });
}
