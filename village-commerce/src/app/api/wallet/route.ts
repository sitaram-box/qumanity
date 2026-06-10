import { NextResponse } from "next/server";
import { createClient, createServiceClient } from "@/lib/supabase/server";
import { getWallet, getTransactions } from "@/lib/wallet";

export async function GET() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const wallet = await getWallet(user.id);
  const transactions = await getTransactions(user.id);
  return NextResponse.json({ wallet, transactions });
}

export async function POST(request: Request) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await request.json();
  const { action, amount, recipient_id } = body;
  const service = await createServiceClient();

  if (action === "transfer" && recipient_id && amount > 0) {
    const senderWallet = await getWallet(user.id);
    if (senderWallet.balance < amount) {
      return NextResponse.json({ error: "Insufficient balance" }, { status: 400 });
    }

    const recipientWallet = await getWallet(recipient_id);
    const senderNew = senderWallet.balance - amount;
    const recipientNew = recipientWallet.balance + amount;

    await service.from("wallets").update({ balance: senderNew }).eq("user_id", user.id);
    await service.from("wallets").update({ balance: recipientNew }).eq("user_id", recipient_id);

    await service.from("transactions").insert([
      {
        wallet_id: senderWallet.id,
        user_id: user.id,
        type: "debit",
        amount: -amount,
        balance_after: senderNew,
        counterparty_id: recipient_id,
        description: "Qoins transfer",
        metadata: { blockchain_ready: true },
      },
      {
        wallet_id: recipientWallet.id,
        user_id: recipient_id,
        type: "credit",
        amount,
        balance_after: recipientNew,
        counterparty_id: user.id,
        description: "Qoins received",
        metadata: { blockchain_ready: true },
      },
    ]);

    return NextResponse.json({ success: true });
  }

  return NextResponse.json({ error: "Invalid action" }, { status: 400 });
}
