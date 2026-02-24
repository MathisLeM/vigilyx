import Link from "next/link";
import Image from "next/image";
import LandingNav from "@/components/LandingNav";

const FEATURES = [
  {
    icon: "🤖",
    title: "Isolation Forest AI engine",
    desc: "A machine learning model trained on your own Stripe history — not generic benchmarks. It learns your revenue patterns and flags what doesn't fit.",
  },
  {
    icon: "🔍",
    title: "Triple-layer anomaly detection",
    desc: "Isolation Forest, MAD, and rolling Z-score run in parallel. When the AI and statistics agree, alerts are marked dual-confirmed — fewer false positives, higher signal.",
  },
  {
    icon: "🔔",
    title: "Slack & email alerts",
    desc: "Get notified the moment an anomaly is detected. Configure per-severity thresholds — HIGH only, or everything — and deliver to your ops channel or inbox.",
  },
  {
    icon: "🏦",
    title: "Up to 5 Stripe accounts",
    desc: "Connect multiple Stripe accounts to one workspace. Each gets its own sync, its own AI model, and its own alert stream.",
  },
  {
    icon: "💡",
    title: "Automatic root-cause hints",
    desc: "Every alert comes with a plain-language explanation. No more staring at a spike and wondering why — the system tells you what likely happened.",
  },
  {
    icon: "📈",
    title: "7 KPIs tracked daily",
    desc: "Revenue, transaction count, average ticket, refund rate, new customers, MRR, and net balance — all computed and monitored automatically from your Stripe data.",
  },
  {
    icon: "⚡",
    title: "Scheduled + on-demand detection",
    desc: "Detection runs automatically every 24 hours. Trigger it manually anytime from the dashboard — full control, zero noise.",
  },
  {
    icon: "🏢",
    title: "Multi-tenant workspaces",
    desc: "Each company gets its own isolated workspace. Data is scoped by tenant at every layer — API, database, ML model, and UI.",
  },
];

const STEPS = [
  {
    number: "01",
    title: "Connect your Stripe account",
    desc: "Add up to 5 named Stripe connections from your Profile. Keys are stored encrypted server-side — never exposed in full.",
  },
  {
    number: "02",
    title: "KPIs sync daily",
    desc: "Revenue, refund rate, average ticket, MRR and more are computed as daily snapshots from your Stripe balance transactions.",
  },
  {
    number: "03",
    title: "Your AI model trains",
    desc: "An Isolation Forest model trains on your account's own history. It learns your seasonal patterns, growth curves, and baseline noise.",
  },
  {
    number: "04",
    title: "Alerts reach your team",
    desc: "Anomalies are ranked by severity with root-cause hints attached. Notifications land in Slack, your inbox, or both — automatically.",
  },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <LandingNav />

      {/* ── Hero ── */}
      <section className="pt-40 pb-24 px-6 text-center relative overflow-hidden">
        {/* Background glow */}
        <div className="absolute inset-0 -z-10">
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[700px] h-[450px]
                          bg-indigo-600/10 blur-[140px] rounded-full" />
        </div>

        <div className="max-w-3xl mx-auto space-y-6">
          <div className="inline-flex items-center gap-2 text-xs font-medium text-indigo-400
                          border border-indigo-800 bg-indigo-950/60 px-3 py-1.5 rounded-full">
            <span className="w-1.5 h-1.5 bg-indigo-400 rounded-full animate-pulse" />
            AI-powered revenue monitoring for Stripe
          </div>

          <h1 className="text-5xl md:text-6xl font-bold tracking-tight text-white leading-tight">
            Your AI watchdog for{" "}
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-violet-400">
              Stripe revenue
            </span>
          </h1>

          <p className="text-lg text-gray-400 max-w-xl mx-auto leading-relaxed">
            Connect your Stripe account. An Isolation Forest model trains on your
            own data, detects statistical anomalies the moment they happen, and
            alerts your team on Slack or email — automatically.
          </p>

          <div className="flex items-center justify-center gap-4 pt-2">
            <Link
              href="/login"
              className="bg-indigo-600 hover:bg-indigo-500 text-white font-semibold
                         px-6 py-3 rounded-xl transition-colors text-sm"
            >
              Get started free
            </Link>
            <a
              href="#how-it-works"
              className="text-sm text-gray-400 hover:text-white transition-colors flex items-center gap-1"
            >
              How it works ↓
            </a>
          </div>
        </div>

        {/* Dashboard mockup */}
        <div className="mt-20 max-w-4xl mx-auto">
          <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden shadow-2xl shadow-black/40">
            {/* Mockup title bar */}
            <div className="border-b border-gray-800 px-4 py-3 flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-red-500/60" />
              <div className="w-3 h-3 rounded-full bg-yellow-500/60" />
              <div className="w-3 h-3 rounded-full bg-green-500/60" />
              <span className="ml-3 text-xs text-gray-600 font-mono">vigilyx-ten.vercel.app/dashboard</span>
            </div>
            {/* Mockup content */}
            <div className="p-6 space-y-4">
              {/* Stat cards row */}
              <div className="grid grid-cols-4 gap-3">
                {[
                  { label: "Total Alerts", value: "14", color: "text-white" },
                  { label: "Unresolved",   value: "6",  color: "text-white" },
                  { label: "🔴 High",      value: "4",  color: "text-red-400" },
                  { label: "🟠 Medium",    value: "2",  color: "text-orange-400" },
                ].map(({ label, value, color }) => (
                  <div key={label} className="bg-gray-800/60 border border-gray-700/50 rounded-xl p-4">
                    <p className="text-xs text-gray-500 mb-1">{label}</p>
                    <p className={`text-2xl font-bold ${color}`}>{value}</p>
                  </div>
                ))}
              </div>
              {/* KPI cards row */}
              <div className="grid grid-cols-7 gap-2">
                {[
                  { label: "Revenue", val: "$13,842", delta: "+12.4%" },
                  { label: "Txns", val: "168", delta: "+3.1%" },
                  { label: "Avg Ticket", val: "$82", delta: "+8.7%" },
                  { label: "Refunds", val: "$284", delta: "-4.2%", neg: true },
                  { label: "Refund %", val: "2.05%", delta: "-0.3%", neg: true },
                  { label: "New Cust.", val: "24", delta: "+0%" },
                  { label: "MRR", val: "$46,200", delta: "+0.9%" },
                ].map(({ label, val, delta, neg }) => (
                  <div key={label} className="bg-gray-800/40 border border-gray-700/40 rounded-lg p-2.5">
                    <p className="text-[10px] text-gray-500 mb-1">{label}</p>
                    <p className="text-xs font-bold text-white leading-tight">{val}</p>
                    <p className={`text-[10px] font-medium mt-0.5 ${neg ? "text-red-400" : "text-emerald-400"}`}>
                      {delta}
                    </p>
                  </div>
                ))}
              </div>
              {/* Fake chart */}
              <div className="bg-gray-800/40 border border-gray-700/40 rounded-xl p-4 h-28 flex items-end gap-1 relative">
                <p className="absolute top-3 left-4 text-xs text-gray-500">Daily Revenue ($)</p>
                {[60, 65, 62, 70, 68, 72, 95, 73, 75, 78, 74, 80, 45, 82, 85, 88, 86, 92, 110, 91].map(
                  (h, i) => (
                    <div
                      key={i}
                      className={`flex-1 rounded-sm transition-all ${
                        h === 110 || h === 95
                          ? "bg-red-500/70"
                          : h === 45
                          ? "bg-red-500/70"
                          : "bg-indigo-500/50"
                      }`}
                      style={{ height: `${h}%` }}
                    />
                  )
                )}
              </div>
              {/* AI badge */}
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center gap-1.5 text-[10px] font-medium text-violet-400
                                 border border-violet-800/60 bg-violet-950/40 px-2.5 py-1 rounded-full">
                  <span className="w-1 h-1 bg-violet-400 rounded-full" />
                  Isolation Forest model active · last trained 6h ago
                </span>
                <span className="inline-flex items-center gap-1.5 text-[10px] font-medium text-emerald-400
                                 border border-emerald-800/60 bg-emerald-950/40 px-2.5 py-1 rounded-full">
                  Slack ✓ · Email ✓
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Features ── */}
      <section id="features" className="py-24 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-3xl font-bold text-white mb-3">
              Built for founders who can&apos;t afford to miss a revenue signal
            </h2>
            <p className="text-gray-400 max-w-xl mx-auto">
              Whether you run a SaaS, a dropshipping store, or an ecommerce brand — Vigilyx watches your Stripe so you don&apos;t have to.
            </p>
          </div>

          <div className="grid md:grid-cols-4 gap-5">
            {FEATURES.map(({ icon, title, desc }) => (
              <div
                key={title}
                className="bg-gray-900 border border-gray-800 rounded-2xl p-6
                           hover:border-gray-700 transition-colors group"
              >
                <div className="text-2xl mb-4">{icon}</div>
                <h3 className="text-white font-semibold mb-2">{title}</h3>
                <p className="text-sm text-gray-400 leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── How it works ── */}
      <section id="how-it-works" className="py-24 px-6 border-t border-gray-800/60">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-3xl font-bold text-white mb-3">How it works</h2>
            <p className="text-gray-400">From zero to AI-powered monitoring in minutes.</p>
          </div>

          <div className="grid md:grid-cols-4 gap-8 relative">
            {/* Connector line (desktop) */}
            <div className="hidden md:block absolute top-8 left-[12.5%] right-[12.5%] h-px bg-gradient-to-r from-indigo-800/0 via-indigo-700/50 to-indigo-800/0" />

            {STEPS.map(({ number, title, desc }) => (
              <div key={number} className="relative text-center space-y-3">
                <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl
                                bg-indigo-950 border border-indigo-800 text-indigo-400
                                font-bold text-lg mx-auto">
                  {number}
                </div>
                <h3 className="text-white font-semibold">{title}</h3>
                <p className="text-sm text-gray-400 leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Social proof / use cases ── */}
      <section className="py-16 px-6 border-t border-gray-800/60">
        <div className="max-w-4xl mx-auto">
          <div className="grid md:grid-cols-3 gap-6">
            {[
              {
                persona: "SaaS founders",
                icon: "🚀",
                text: "Catch MRR drops and refund spikes before your next board meeting. Know if a pricing change moved the needle.",
              },
              {
                persona: "Ecommerce & DTC",
                icon: "🛒",
                text: "Detect flash-sale anomalies, fraud patterns, and conversion drops in real time — across all your Stripe accounts.",
              },
              {
                persona: "Dropshippers",
                icon: "📦",
                text: "Monitor margin-sensitive metrics daily. Get alerted the moment refund rate or avg ticket moves outside your normal range.",
              },
            ].map(({ persona, icon, text }) => (
              <div key={persona} className="bg-gray-900/60 border border-gray-800 rounded-2xl p-6 space-y-3">
                <div className="text-2xl">{icon}</div>
                <h3 className="text-white font-semibold">{persona}</h3>
                <p className="text-sm text-gray-400 leading-relaxed">{text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Final CTA ── */}
      <section className="py-24 px-6 border-t border-gray-800/60">
        <div className="max-w-2xl mx-auto text-center space-y-6">
          <h2 className="text-3xl font-bold text-white">
            Stop discovering problems in hindsight.
          </h2>
          <p className="text-gray-400">
            Sign in with a demo account and explore the AI dashboard — no Stripe account needed to get started.
          </p>
          <Link
            href="/login"
            className="inline-block bg-indigo-600 hover:bg-indigo-500 text-white font-semibold
                       px-8 py-3.5 rounded-xl transition-colors text-sm"
          >
            Start monitoring →
          </Link>
          <p className="text-xs text-gray-600 pt-2">
            Demo: <span className="text-gray-500">acme@demo.com</span> / <span className="text-gray-500">demo1234</span>
          </p>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="border-t border-gray-800/60 py-8 px-6">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3 text-sm text-gray-600">
            <Image src="/vigilyx_logo.png" alt="Vigilyx" width={80} height={20} className="h-5 w-auto opacity-50" />
            <span>— AI revenue monitoring for Stripe</span>
          </div>
          <div className="flex items-center gap-6 text-xs text-gray-600">
            <Link href="/login" className="hover:text-gray-400 transition-colors">Sign in</Link>
            <Link href="/dashboard" className="hover:text-gray-400 transition-colors">Dashboard</Link>
            <Link href="/profile" className="hover:text-gray-400 transition-colors">Profile</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
