"use client";

import { useEffect, useState, useRef, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { Send } from "lucide-react";

interface Message {
  id: string;
  sender_id: string;
  content: string | null;
  image_url: string | null;
  created_at: string;
  profiles?: { full_name: string };
}

function ChatContent() {
  const searchParams = useSearchParams();
  const chatId = searchParams.get("id");
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [userId, setUserId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const supabase = createClient();

  useEffect(() => {
    supabase.auth.getUser().then(({ data }) => setUserId(data.user?.id ?? null));
  }, [supabase.auth]);

  useEffect(() => {
    if (!chatId) return;

    fetch(`/api/chat?chat_id=${chatId}`)
      .then((r) => r.json())
      .then((d) => setMessages(d.messages ?? []));

    const channel = supabase
      .channel(`chat-${chatId}`)
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "messages", filter: `chat_id=eq.${chatId}` },
        (payload) => {
          setMessages((m) => [...m, payload.new as Message]);
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [chatId, supabase]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() || !chatId) return;

    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "send", chat_id: chatId, content: input }),
    });
    const data = await res.json();
    if (data.message) {
      setMessages((m) => [...m, data.message]);
    }
    setInput("");
  }

  if (!chatId) {
    return (
      <div className="mx-auto max-w-lg px-4 py-12 text-center">
        <p className="text-soil/70">Select a provider from marketplace to start chatting.</p>
      </div>
    );
  }

  return (
    <div className="mx-auto flex h-[calc(100vh-8rem)] max-w-2xl flex-col px-4 py-4">
      <h1 className="mb-4 text-xl font-bold">Chat</h1>

      <div className="flex-1 space-y-3 overflow-y-auto">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.sender_id === userId ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-2 ${
                msg.sender_id === userId ? "bg-saffron text-white" : "border border-wheat bg-white"
              }`}
            >
              {msg.profiles?.full_name && msg.sender_id !== userId && (
                <p className="text-xs opacity-70">{msg.profiles.full_name}</p>
              )}
              <p className="text-sm">{msg.content}</p>
              {msg.image_url && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={msg.image_url} alt="Shared" className="mt-2 max-h-40 rounded-lg" />
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={send} className="flex gap-2 border-t border-wheat pt-4">
        <input
          className="input flex-1"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type a message..."
        />
        <button type="submit" className="btn-primary !px-4">
          <Send className="h-5 w-5" />
        </button>
      </form>
    </div>
  );
}

export default function ChatPage() {
  return (
    <Suspense fallback={<div className="p-8">Loading chat...</div>}>
      <ChatContent />
    </Suspense>
  );
}
