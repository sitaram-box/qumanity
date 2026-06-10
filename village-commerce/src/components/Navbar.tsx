"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, X, Wallet, MessageCircle, Home, Store, Bot, Truck, Shield } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";

const links = [
  { href: "/", label: "Home", icon: Home },
  { href: "/marketplace", label: "Market", icon: Store },
  { href: "/employment", label: "Jobs", icon: Home },
  { href: "/assistant", label: "AI Help", icon: Bot },
  { href: "/wallet", label: "Qoins", icon: Wallet },
  { href: "/delivery", label: "Delivery", icon: Truck },
  { href: "/chat", label: "Chat", icon: MessageCircle },
  { href: "/admin", label: "Council", icon: Shield },
];

export function Navbar() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 border-b border-wheat bg-white/95 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <Link href="/" className="flex items-center gap-2">
          <span className="flex h-10 w-10 items-center justify-center rounded-full bg-saffron text-lg font-bold text-white">
            व
          </span>
          <div>
            <p className="text-sm font-bold leading-tight text-soil">Village Commerce</p>
            <p className="text-xs text-earth-green">Qumanity</p>
          </div>
        </Link>

        <nav className="hidden items-center gap-1 md:flex">
          {links.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className={cn(
                "rounded-lg px-3 py-2 text-sm font-medium transition",
                pathname === href
                  ? "bg-saffron/15 text-saffron-dark"
                  : "text-soil hover:bg-wheat/50"
              )}
            >
              {label}
            </Link>
          ))}
          <Link href="/auth/login" className="btn-primary ml-2 !py-2 !text-sm">
            Login
          </Link>
        </nav>

        <button
          type="button"
          className="rounded-lg p-2 md:hidden"
          onClick={() => setOpen(!open)}
          aria-label="Menu"
        >
          {open ? <X /> : <Menu />}
        </button>
      </div>

      {open && (
        <nav className="border-t border-wheat px-4 py-3 md:hidden">
          {links.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              onClick={() => setOpen(false)}
              className="flex items-center gap-3 rounded-lg px-3 py-3 text-base font-medium hover:bg-wheat/50"
            >
              <Icon className="h-5 w-5 text-saffron" />
              {label}
            </Link>
          ))}
          <Link href="/auth/login" className="btn-primary mt-2 w-full" onClick={() => setOpen(false)}>
            Login / Register
          </Link>
        </nav>
      )}
    </header>
  );
}

export function Footer() {
  return (
    <footer className="mt-auto border-t border-wheat bg-white py-8">
      <div className="mx-auto max-w-6xl px-4 text-center text-sm text-soil/70">
        <p className="font-semibold text-soil">Village Employment & Local Commerce System</p>
        <p className="mt-1">Qumanity · Gaanv ki digital economy · Verified by Village Council</p>
        <p className="mt-3 text-xs">🇮🇳 Hindi-first · PWA ready · Qoins powered</p>
      </div>
    </footer>
  );
}
