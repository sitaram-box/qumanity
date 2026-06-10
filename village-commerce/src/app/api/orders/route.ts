import { NextResponse } from "next/server";
import { createClient, createServiceClient } from "@/lib/supabase/server";
import { holdEscrow } from "@/lib/wallet";
import { createDeliveryTask, assignOtpToOrder } from "@/lib/delivery";

export async function POST(request: Request) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await request.json();
  const {
    order_type,
    provider_id,
    seller_id,
    service_provider_id,
    total_qoins,
    delivery_qoins = 0,
    notes,
    village_id,
    delivery_address,
    delivery_lat,
    delivery_lng,
    items = [],
    needs_delivery = false,
  } = body;

  const service = await createServiceClient();

  const { data: order, error } = await service
    .from("orders")
    .insert({
      customer_id: user.id,
      provider_id,
      seller_id,
      service_provider_id,
      order_type,
      total_qoins,
      delivery_qoins,
      notes,
      village_id,
      delivery_address,
      delivery_lat,
      delivery_lng,
      status: "pending",
    })
    .select()
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 400 });

  if (items.length > 0) {
    await service.from("order_items").insert(
      items.map((item: { product_id: string; quantity: number; unit_price: number }) => ({
        order_id: order.id,
        product_id: item.product_id,
        quantity: item.quantity,
        unit_price: item.unit_price,
        subtotal: item.quantity * item.unit_price,
      }))
    );
  }

  try {
    const txId = await holdEscrow(
      user.id,
      total_qoins,
      order.id,
      `Escrow for order ${order.id.slice(0, 8)}`
    );
    await service
      .from("orders")
      .update({ status: "in_escrow", escrow_transaction_id: txId })
      .eq("id", order.id);
  } catch (e) {
    await service.from("orders").update({ status: "cancelled" }).eq("id", order.id);
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Payment failed" },
      { status: 400 }
    );
  }

  if (needs_delivery) {
    const otp = await assignOtpToOrder(order.id);
    await createDeliveryTask(order.id);
    return NextResponse.json({ order: { ...order, otp_code: otp } });
  }

  return NextResponse.json({ order });
}

export async function GET(request: Request) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { searchParams } = new URL(request.url);
  const role = searchParams.get("role") ?? "customer";

  let q = supabase.from("orders").select("*, order_items(*)");
  if (role === "provider") {
    q = q.eq("provider_id", user.id);
  } else {
    q = q.eq("customer_id", user.id);
  }

  const { data } = await q.order("created_at", { ascending: false });
  return NextResponse.json({ orders: data ?? [] });
}
