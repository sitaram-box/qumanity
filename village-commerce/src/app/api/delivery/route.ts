import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import {
  acceptDelivery,
  updateDeliveryStatus,
  completeDeliveryWithOtp,
  getAgentTasks,
} from "@/lib/delivery";

export async function GET() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const tasks = await getAgentTasks(user.id);
  return NextResponse.json({ tasks });
}

export async function POST(request: Request) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await request.json();
  const { action, task_id, order_id, otp, status } = body;

  try {
    switch (action) {
      case "accept": {
        const task = await acceptDelivery(task_id, user.id);
        return NextResponse.json({ task });
      }
      case "update_status": {
        const task = await updateDeliveryStatus(task_id, status, user.id);
        return NextResponse.json({ task });
      }
      case "complete": {
        const result = await completeDeliveryWithOtp(order_id, otp);
        return NextResponse.json(result);
      }
      default:
        return NextResponse.json({ error: "Unknown action" }, { status: 400 });
    }
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Delivery error" },
      { status: 400 }
    );
  }
}
