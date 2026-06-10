import Link from "next/link";
import { CategoryGrid } from "@/components/CategoryGrid";
import { Store, Users, Bot, ShieldCheck, Coins, Truck } from "lucide-react";

export default function HomePage() {
  return (
    <div>
      <section className="gradient-hero px-4 py-16 md:py-24">
        <div className="mx-auto max-w-6xl text-center">
          <p className="mb-2 text-sm font-semibold uppercase tracking-wider text-earth-green">
            Qumanity · Village Economy
          </p>
          <h1 className="text-3xl font-bold leading-tight text-soil md:text-5xl">
            Gaanv ki Digital Economy
            <br />
            <span className="text-saffron-dark">Employment · Commerce · Trust</span>
          </h1>
          <p className="mx-auto mt-4 max-w-2xl text-base text-soil/80 md:text-lg">
            Hire local workers, buy village products, pay with Qoins, and get verified by your
            Village Council (Quantum Punch). Built for rural India — simple, fast, trustworthy.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Link href="/marketplace" className="btn-primary">
              <Store className="h-5 w-5" />
              Browse Marketplace
            </Link>
            <Link href="/assistant" className="btn-secondary">
              <Bot className="h-5 w-5" />
              AI Assistant
            </Link>
            <Link href="/register" className="btn-secondary">
              Register as Provider
            </Link>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-12">
        <h2 className="section-title mb-6 text-center">How It Works</h2>
        <div className="grid gap-4 md:grid-cols-3">
          {[
            {
              icon: Users,
              title: "Register & Verify",
              desc: "Choose your role — worker, provider, seller, or delivery agent. Village Council approves with a Verified badge.",
            },
            {
              icon: Store,
              title: "Trade Locally",
              desc: "Browse services and products in your village. Book instantly with Available Now and emergency options.",
            },
            {
              icon: Coins,
              title: "Pay with Qoins",
              desc: "Secure escrow payments. Qoins released only when service or delivery is complete.",
            },
          ].map(({ icon: Icon, title, desc }) => (
            <div key={title} className="card text-center">
              <Icon className="mx-auto h-10 w-10 text-saffron" />
              <h3 className="mt-3 font-bold">{title}</h3>
              <p className="mt-2 text-sm text-soil/70">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="bg-white py-12">
        <div className="mx-auto max-w-6xl px-4">
          <h2 className="section-title mb-2">Categories</h2>
          <p className="mb-6 text-soil/70">Travel · Food · Labour · Education · Repair · Health · More</p>
          <CategoryGrid />
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-12">
        <div className="grid gap-4 md:grid-cols-2">
          <Link href="/employment" className="card flex items-center gap-4 transition hover:border-earth-green">
            <Users className="h-12 w-12 text-earth-green" />
            <div>
              <h3 className="font-bold">Employment Exchange</h3>
              <p className="text-sm text-soil/70">Find verified labourers and skilled workers nearby</p>
            </div>
          </Link>
          <Link href="/delivery" className="card flex items-center gap-4 transition hover:border-saffron">
            <Truck className="h-12 w-12 text-saffron" />
            <div>
              <h3 className="font-bold">Hyperlocal Delivery</h3>
              <p className="text-sm text-soil/70">Village agents deliver products with live tracking</p>
            </div>
          </Link>
          <Link href="/admin" className="card flex items-center gap-4 transition hover:border-soil">
            <ShieldCheck className="h-12 w-12 text-soil" />
            <div>
              <h3 className="font-bold">Village Council Dashboard</h3>
              <p className="text-sm text-soil/70">Verify profiles, manage disputes, track village economy</p>
            </div>
          </Link>
          <Link href="/wallet" className="card flex items-center gap-4 transition hover:border-saffron">
            <Coins className="h-12 w-12 text-saffron-dark" />
            <div>
              <h3 className="font-bold">Qoins Wallet</h3>
              <p className="text-sm text-soil/70">Balance, transactions, escrow — village digital currency</p>
            </div>
          </Link>
        </div>
      </section>
    </div>
  );
}
