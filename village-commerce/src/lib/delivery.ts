import { createServiceClient } from "@/lib/supabase/server";
import { findNearbyAgents } from "@/lib/geo";
import { releaseEscrow } from "@/lib/wallet";
import { generateOtp, haversineKm } from "@/lib/utils";

export async function createDeliveryTask(orderId: string) {
  const supabase = await createServiceClient();

  const { data: order } = await supabase
    .from("orders")
    .select("*")
    .eq("id", orderId)
    .single();
  if (!order) throw new Error("Order not found");

  const dropLat = order.delivery_lat;
  const dropLng = order.delivery_lng;

  let distanceKm: number | null = null;
  let estimatedMinutes: number | null = 30;

  if (dropLat && dropLng) {
    const agents = await findNearbyAgents(dropLat, dropLng, 15);
    if (agents.length > 0 && agents[0].current_lat && agents[0].current_lng) {
      distanceKm = haversineKm(
        dropLat,
        dropLng,
        agents[0].current_lat,
        agents[0].current_lng
      );
      estimatedMinutes = Math.max(15, Math.round(distanceKm * 8));
    }
  }

  const { data: task, error } = await supabase
    .from("delivery_tasks")
    .insert({
      order_id: orderId,
      status: "notified",
      drop_lat: dropLat,
      drop_lng: dropLng,
      distance_km: distanceKm,
      estimated_minutes: estimatedMinutes,
    })
    .select("*")
    .single();
  if (error) throw new Error(error.message);

  await supabase
    .from("orders")
    .update({ status: "in_delivery" })
    .eq("id", orderId);

  return task;
}

export async function acceptDelivery(taskId: string, agentUserId: string) {
  const supabase = await createServiceClient();

  const { data: agent } = await supabase
    .from("delivery_agents")
    .select("id")
    .eq("user_id", agentUserId)
    .eq("is_active", true)
    .single();
  if (!agent) throw new Error("Not an active delivery agent");

  const { data: task, error } = await supabase
    .from("delivery_tasks")
    .update({
      agent_id: agent.id,
      status: "accepted",
      accepted_at: new Date().toISOString(),
    })
    .eq("id", taskId)
    .eq("status", "notified")
    .select("*")
    .single();

  if (error || !task) throw new Error("Task already accepted or not found");
  return task;
}

export async function updateDeliveryStatus(
  taskId: string,
  status: "picked_up" | "en_route" | "delivered",
  agentUserId: string
) {
  const supabase = await createServiceClient();

  const { data: agent } = await supabase
    .from("delivery_agents")
    .select("id")
    .eq("user_id", agentUserId)
    .single();
  if (!agent) throw new Error("Not a delivery agent");

  const updates: Record<string, unknown> = { status };
  if (status === "picked_up") updates.picked_up_at = new Date().toISOString();
  if (status === "delivered") updates.delivered_at = new Date().toISOString();

  const { data: task, error } = await supabase
    .from("delivery_tasks")
    .update(updates)
    .eq("id", taskId)
    .eq("agent_id", agent.id)
    .select("*, orders(*)")
    .single();
  if (error) throw new Error(error.message);

  if (status === "delivered" && task) {
    const order = task.orders as {
      id: string;
      customer_id: string;
      provider_id: string | null;
      total_qoins: number;
      delivery_qoins: number;
      otp_code: string | null;
    };
    await supabase.from("orders").update({ status: "delivered" }).eq("id", order.id);
  }

  return task;
}

export async function completeDeliveryWithOtp(orderId: string, otp: string) {
  const supabase = await createServiceClient();

  const { data: order } = await supabase
    .from("orders")
    .select("*")
    .eq("id", orderId)
    .single();
  if (!order) throw new Error("Order not found");
  if (order.otp_code && order.otp_code !== otp) throw new Error("Invalid OTP");

  const providerShare = order.total_qoins - (order.delivery_qoins ?? 0);
  const recipients: { userId: string; amount: number; description: string }[] = [];

  if (order.provider_id && providerShare > 0) {
    recipients.push({
      userId: order.provider_id,
      amount: providerShare,
      description: "Payment for order (escrow release)",
    });
  }

  const { data: task } = await supabase
    .from("delivery_tasks")
    .select("agent_id, delivery_agents(user_id)")
    .eq("order_id", orderId)
    .single();

  if (task?.delivery_agents && order.delivery_qoins > 0) {
    const agent = task.delivery_agents as { user_id: string };
    recipients.push({
      userId: agent.user_id,
      amount: order.delivery_qoins,
      description: "Delivery fee (escrow release)",
    });
  }

  await releaseEscrow(orderId, recipients);

  await supabase
    .from("orders")
    .update({
      status: "completed",
      otp_verified: true,
      completed_at: new Date().toISOString(),
    })
    .eq("id", orderId);

  if (task?.agent_id) {
    await supabase.rpc("increment_delivery_count", { agent_id: task.agent_id }).maybeSingle();
  }

  return { success: true };
}

export async function assignOtpToOrder(orderId: string) {
  const supabase = await createServiceClient();
  const otp = generateOtp();
  await supabase.from("orders").update({ otp_code: otp }).eq("id", orderId);
  return otp;
}

export async function getAgentTasks(agentUserId: string) {
  const supabase = await createServiceClient();
  const { data: agent } = await supabase
    .from("delivery_agents")
    .select("id")
    .eq("user_id", agentUserId)
    .single();
  if (!agent) return [];

  const { data } = await supabase
    .from("delivery_tasks")
    .select("*, orders(*)")
    .or(`agent_id.eq.${agent.id},and(agent_id.is.null,status.eq.notified)`)
    .order("created_at", { ascending: false });

  return data ?? [];
}
