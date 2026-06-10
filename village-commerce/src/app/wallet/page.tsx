"use client";

import { useEffect, useState } from "react";
import { formatQoins } from "@/lib/utils";
import { Coins, ArrowUpRight, ArrowDownLeft } from "lucide-react";
import type { Transaction, Wallet } from "@/lib/types";

export default function WalletPage() {
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/wallet")
      .then((r) => r.json())
      .then((d) => {
        setWallet(d.wallet);
        setTransactions(d.transactions ?? []);
        setLoading(false);
      });
  }, []);

  if (loading) return <div className="p-8 text-center">Loading wallet...</div>;

  return (
    <div className="mx-auto max-w-lg px-4 py-8">
      <h1 className="section-title mb-6">Qoins Wallet</h1>

      <div className="card mb-6 bg-gradient-to-br from-saffron to-saffron-dark text-white">
        <div className="flex items-center gap-2 opacity-90">
          <Coins className="h-5 w-5" />
          <span className="text-sm">Available Balance</span>
        </div>
        <p className="mt-2 text-4xl font-bold">{formatQoins(wallet?.balance ?? 0)}</p>
        <p className="mt-1 text-xs opacity-80">Village digital currency · Escrow protected</p>
      </div>

      <h2 className="mb-3 font-bold">Transaction History</h2>
      {transactions.length === 0 ? (
        <p className="text-sm text-soil/60">No transactions yet</p>
      ) : (
        <ul className="space-y-2">
          {transactions.map((tx) => (
            <li key={tx.id} className="card flex items-center justify-between !py-3">
              <div className="flex items-center gap-3">
                {tx.amount > 0 ? (
                  <ArrowDownLeft className="h-5 w-5 text-earth-green" />
                ) : (
                  <ArrowUpRight className="h-5 w-5 text-red-500" />
                )}
                <div>
                  <p className="text-sm font-medium">{tx.description ?? tx.type}</p>
                  <p className="text-xs text-soil/50">
                    {new Date(tx.created_at).toLocaleDateString("en-IN")}
                  </p>
                </div>
              </div>
              <span className={`font-bold ${tx.amount > 0 ? "text-earth-green" : "text-red-600"}`}>
                {tx.amount > 0 ? "+" : ""}
                {tx.amount}
              </span>
            </li>
          ))}
        </ul>
      )}

      <p className="mt-6 text-xs text-soil/50">
        Architecture ready for blockchain / quantum ledger integration. Transaction metadata stored
        with each entry.
      </p>
    </div>
  );
}
