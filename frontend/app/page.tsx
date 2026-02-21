import Link from "next/link";
import LandingNav from "@/components/LandingNav";

const FEATURES = [
  {
    icon: "🔍",
    title: "Dual-method anomaly detection",
    desc: "MAD and rolling Z-score run in parallel on every metric. When both agree, the alert is marked dual-confirmed — meaning fewer false positives and higher confidence.",
  },
  {
    icon: "💡",
    title: "Automatic root-cause hints",
    desc: "Every alert comes with a plain-language explanation. No more staring at a spike and wondering why — the system tells you what likely happened.",
  },
  {
    icon: "📈",
    title: "7 Stripe KPIs tracked daily",
    desc: "Revenue, transaction count, average ticket, refund rate, new customers, and MRR — all computed and monitored automatically from your Stripe data.",
  },
  {
    icon: "🏢",
    title: "Multi-tenant architecture",
    desc: "Each company gets its own isolated workspace. Data is scoped by tenant at every layer — API, database, and UI.",
  },
  {
    icon: "⚡",
    title: "On-demand or scheduled detection",
    desc: "Run detection manually from the dashboard or let the scheduler run it automatically every 24 hours. Full control, zero noise.",
  },
  {
    icon: "🔑",
    title: "Stripe API key integration",
    desc: "Connect your Stripe account with a secret key. It's stored server-side, never exposed in full, and used exclusively to pull your own data.",
  },
];

const STEPS = [
  {
    number: "01",
    title: "Connect your Stripe account",
    desc: "Add your Stripe secret key in your Profile settings. The key is stored securely server-side.",
  },
  {
    number: "02",
    title: "KPIs are computed automatically",
    desc: "Daily revenue, refund rate, new customers, MRR and more are calculated and stored as daily snapshots.",
  },
  {
    number: "03",
    title: "Anomalies are detected & surfaced",
    desc: "Statistical models run over your history. Outliers are ranked by severity and severity, with root-cause hints attached.",
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
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[400px]
                          bg-indigo-600/10 blur-[120px] rounded-full" />
        </div>

        <div className="max-w-3xl mx-auto space-y-6">
          <div className="inline-flex items-center gap-2 text-xs font-medium text-indigo-400
                          border border-indigo-800 bg-indigo-950/60 px-3 py-1.5 rounded-full">
            <span className="w-1.5 h-1.5 bg-indigo-400 rounded-full animate-pulse" />
            Statistical anomaly detection for Stripe
          </div>

          <h1 className="text-5xl md:text-6xl font-bold tracking-tight text-white leading-tight">
            Know when your{" "}
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-violet-400">
              revenue behaves
            </span>{" "}
            unexpectedly
          </h1>

          <p className="text-lg text-gray-400 max-w-xl mx-auto leading-relaxed">
            Connect your Stripe account. We compute your KPIs daily, detect
            statistical anomalies using MAD &amp; rolling Z-score, and surface
            root-cause hints — automatically.
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
              <span className="ml-3 text-xs text-gray-600 font-mono">localhost:3000/dashboard</span>
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
            </div>
          </div>
        </div>
      </section>

      {/* ── Features ── */}
      <section id="features" className="py-24 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-3xl font-bold text-white mb-3">
              Everything you need to monitor Stripe
            </h2>
            <p className="text-gray-400 max-w-xl mx-auto">
              Built for ops and finance teams who want to catch revenue anomalies before they become real problems.
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-5">
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
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-3xl font-bold text-white mb-3">How it works</h2>
            <p className="text-gray-400">Up and running in minutes.</p>
          </div>

          <div className="grid md:grid-cols-3 gap-8 relative">
            {/* Connector line (desktop) */}
            <div className="hidden md:block absolute top-8 left-[16.5%] right-[16.5%] h-px bg-gradient-to-r from-indigo-800/0 via-indigo-700/50 to-indigo-800/0" />

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

      {/* ── Final CTA ── */}
      <section className="py-24 px-6 border-t border-gray-800/60">
        <div className="max-w-2xl mx-auto text-center space-y-6">
          <h2 className="text-3xl font-bold text-white">
            Ready to catch anomalies before they hurt?
          </h2>
          <p className="text-gray-400">
            Sign in with a demo account and explore the dashboard — no Stripe account needed to get started.
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
            <img src="/vigilyx_logo.png" alt="Vigilyx" className="h-5 w-auto opacity-50" />
            <span>— Stripe anomaly detection</span>
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
