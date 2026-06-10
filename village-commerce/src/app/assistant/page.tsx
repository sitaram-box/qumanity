"use client";

import { useState, useRef, useEffect } from "react";
import { ListingCard } from "@/components/ListingCard";
import type { AIRecommendation } from "@/lib/types";
import { Bot, Send } from "lucide-react";
import { useRouter } from "next/navigation";

interface Message {
  role: "user" | "assistant";
  content: string;
  recommendations?: AIRecommendation[];
}

export default function AssistantPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content:
        "Namaste! 🙏 Main aapki madad karunga — plumber, sabzi, tuition, labour... kuch bhi poochhiye!",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const router = useRouter();

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMsg = input.trim();
    setInput("");
    setMessages((m) => [...m, { role: "user", content: userMsg }]);
    setLoading(true);

    const res = await fetch("/api/ai", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: userMsg }),
    });
    const data = await res.json();
    setLoading(false);

    setMessages((m) => [
      ...m,
      {
        role: "assistant",
        content: data.reply ?? "Sorry, kuch problem hui.",
        recommendations: data.recommendations,
      },
    ]);
  }

  async function selectProvider(item: AIRecommendation) {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "create", participant_id: item.userId }),
    });
    const data = await res.json();
    if (data.chat) router.push(`/chat?id=${data.chat.id}`);
  }

  return (
    <div className="mx-auto flex h-[calc(100vh-8rem)] max-w-2xl flex-col px-4 py-4">
      <div className="mb-4 flex items-center gap-2">
        <Bot className="h-8 w-8 text-saffron" />
        <div>
          <h1 className="text-xl font-bold">AI Assistant</h1>
          <p className="text-xs text-soil/60">Gaanv ki services dhundhein</p>
        </div>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto pb-4">
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                msg.role === "user"
                  ? "bg-saffron text-white"
                  : "border border-wheat bg-white text-soil"
              }`}
            >
              <p className="text-sm">{msg.content}</p>
              {msg.recommendations && msg.recommendations.length > 0 && (
                <div className="mt-3 space-y-2">
                  {msg.recommendations.slice(0, 4).map((r) => (
                    <ListingCard key={r.id} item={r} onSelect={selectProvider} />
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {loading && <p className="text-sm text-soil/50">Searching village database...</p>}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={send} className="flex gap-2 border-t border-wheat pt-4">
        <input
          className="input flex-1"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="I need a plumber near me..."
        />
        <button type="submit" className="btn-primary !px-4" disabled={loading}>
          <Send className="h-5 w-5" />
        </button>
      </form>

      <div className="mt-2 flex flex-wrap gap-2">
        {["Plumber near me", "Vegetables delivered", "Class 8 tuition", "Cheapest labour"].map(
          (s) => (
            <button
              key={s}
              type="button"
              className="rounded-full border border-wheat px-3 py-1 text-xs hover:bg-wheat/50"
              onClick={() => setInput(s)}
            >
              {s}
            </button>
          )
        )}
      </div>
    </div>
  );
}
