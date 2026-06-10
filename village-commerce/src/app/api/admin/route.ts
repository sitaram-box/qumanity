import { NextResponse } from "next/server";
import { createClient, createServiceClient } from "@/lib/supabase/server";
import {
  approveVerification,
  rejectVerification,
  getPendingVerifications,
  getAdminAnalytics,
} from "@/lib/verification";
import { getVillageEconomyStats } from "@/lib/wallet";

async function requireCouncil(userId: string) {
  const service = await createServiceClient();
  const { data: profile } = await service
    .from("profiles")
    .select("roles, village_id")
    .eq("id", userId)
    .single();
  const roles = profile?.roles ?? [];
  if (!roles.includes("village_council") && !roles.includes("super_admin")) {
    throw new Error("Forbidden");
  }
  return profile;
}

export async function GET(request: Request) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  try {
    const profile = await requireCouncil(user.id);
    const { searchParams } = new URL(request.url);
    const view = searchParams.get("view");

    if (view === "analytics") {
      const analytics = await getAdminAnalytics();
      return NextResponse.json({ analytics });
    }

    if (view === "economy" && profile?.village_id) {
      const economy = await getVillageEconomyStats(profile.village_id);
      return NextResponse.json({ economy });
    }

    const pending = await getPendingVerifications(profile?.village_id ?? undefined);
    return NextResponse.json({ pending });
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Error" },
      { status: 403 }
    );
  }
}

export async function POST(request: Request) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  try {
    await requireCouncil(user.id);
    const body = await request.json();
    const { action, application_id, notes } = body;

    if (action === "approve") {
      const app = await approveVerification(application_id, user.id, notes);
      return NextResponse.json({ application: app });
    }
    if (action === "reject") {
      const app = await rejectVerification(application_id, user.id, notes ?? "Rejected");
      return NextResponse.json({ application: app });
    }

    return NextResponse.json({ error: "Unknown action" }, { status: 400 });
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Error" },
      { status: 400 }
    );
  }
}
