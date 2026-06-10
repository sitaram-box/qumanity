import { NextResponse } from "next/server";
import { createClient, createServiceClient } from "@/lib/supabase/server";

export async function GET(request: Request) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { searchParams } = new URL(request.url);
  const chatId = searchParams.get("chat_id");

  if (chatId) {
    const { data } = await supabase
      .from("messages")
      .select("*, profiles(full_name, avatar_url)")
      .eq("chat_id", chatId)
      .order("created_at", { ascending: true });
    return NextResponse.json({ messages: data ?? [] });
  }

  const { data } = await supabase
    .from("chats")
    .select("*")
    .contains("participant_ids", [user.id])
    .order("last_message_at", { ascending: false, nullsFirst: false });

  return NextResponse.json({ chats: data ?? [] });
}

export async function POST(request: Request) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await request.json();
  const { action, participant_id, order_id, chat_id, content, image_url, quotation } = body;
  const service = await createServiceClient();

  if (action === "create") {
    const participantIds = [user.id, participant_id].sort();
    const { data: chat, error } = await service
      .from("chats")
      .insert({
        chat_type: order_id ? "order_negotiation" : "customer_provider",
        order_id: order_id ?? null,
        participant_ids: participantIds,
      })
      .select()
      .single();
    if (error) return NextResponse.json({ error: error.message }, { status: 400 });
    return NextResponse.json({ chat });
  }

  if (action === "send" && chat_id) {
    const { data: message, error } = await service
      .from("messages")
      .insert({
        chat_id,
        sender_id: user.id,
        content,
        image_url,
        quotation,
      })
      .select()
      .single();
    if (error) return NextResponse.json({ error: error.message }, { status: 400 });

    await service
      .from("chats")
      .update({ last_message_at: new Date().toISOString() })
      .eq("id", chat_id);

    return NextResponse.json({ message });
  }

  return NextResponse.json({ error: "Invalid action" }, { status: 400 });
}
