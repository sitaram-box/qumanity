import { createServiceClient } from "@/lib/supabase/server";

export async function getWallet(userId: string) {
  const supabase = await createServiceClient();
  const { data, error } = await supabase
    .from("wallets")
    .select("*")
    .eq("user_id", userId)
    .single();
  if (error) throw new Error(error.message);
  return data;
}

export async function getTransactions(userId: string, limit = 50) {
  const supabase = await createServiceClient();
  const { data, error } = await supabase
    .from("transactions")
    .select("*")
    .eq("user_id", userId)
    .order("created_at", { ascending: false })
    .limit(limit);
  if (error) throw new Error(error.message);
  return data ?? [];
}

export async function holdEscrow(
  customerId: string,
  amount: number,
  orderId: string,
  description: string
): Promise<string> {
  const supabase = await createServiceClient();

  const wallet = await getWallet(customerId);
  if (wallet.balance < amount) {
    throw new Error("Insufficient Qoins balance");
  }

  const newBalance = wallet.balance - amount;
  const { error: walletErr } = await supabase
    .from("wallets")
    .update({ balance: newBalance, updated_at: new Date().toISOString() })
    .eq("user_id", customerId);
  if (walletErr) throw new Error(walletErr.message);

  const { data: tx, error: txErr } = await supabase
    .from("transactions")
    .insert({
      wallet_id: wallet.id,
      user_id: customerId,
      type: "escrow_hold",
      amount: -amount,
      balance_after: newBalance,
      order_id: orderId,
      description,
      metadata: { escrow: true, blockchain_ready: true },
    })
    .select("id")
    .single();
  if (txErr) throw new Error(txErr.message);

  return tx.id;
}

export async function releaseEscrow(
  orderId: string,
  recipients: { userId: string; amount: number; description: string }[]
) {
  const supabase = await createServiceClient();

  for (const r of recipients) {
    const wallet = await getWallet(r.userId);
    const newBalance = wallet.balance + r.amount;

    await supabase
      .from("wallets")
      .update({ balance: newBalance, updated_at: new Date().toISOString() })
      .eq("user_id", r.userId);

    await supabase.from("transactions").insert({
      wallet_id: wallet.id,
      user_id: r.userId,
      type: "escrow_release",
      amount: r.amount,
      balance_after: newBalance,
      order_id: orderId,
      description: r.description,
      metadata: { escrow_release: true, blockchain_ready: true },
    });
  }
}

export async function creditWallet(
  userId: string,
  amount: number,
  description: string,
  type: "credit" | "bonus" = "credit"
) {
  const supabase = await createServiceClient();
  const wallet = await getWallet(userId);
  const newBalance = wallet.balance + amount;

  await supabase
    .from("wallets")
    .update({ balance: newBalance })
    .eq("user_id", userId);

  await supabase.from("transactions").insert({
    wallet_id: wallet.id,
    user_id: userId,
    type,
    amount,
    balance_after: newBalance,
    description,
    metadata: { blockchain_ready: true },
  });
}

export async function getVillageEconomyStats(villageId: string) {
  const supabase = await createServiceClient();

  const { count: providers } = await supabase
    .from("service_providers")
    .select("*", { count: "exact", head: true })
    .eq("is_active", true);

  const { data: orders } = await supabase
    .from("orders")
    .select("total_qoins, order_type")
    .eq("village_id", villageId)
    .in("status", ["completed", "delivered"]);

  const totalSpent = (orders ?? []).reduce((s, o) => s + o.total_qoins, 0);

  const { data: wallets } = await supabase.from("wallets").select("balance");
  const circulation = (wallets ?? []).reduce((s, w) => s + w.balance, 0);

  return {
    total_qoins_circulation: circulation,
    total_spent: totalSpent,
    active_providers: providers ?? 0,
    order_count: orders?.length ?? 0,
  };
}
