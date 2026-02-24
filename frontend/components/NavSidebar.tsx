"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

interface Props {
  children?: React.ReactNode; // page-specific controls injected between nav and disconnect
}

export default function NavSidebar({ children }: Props) {
  const { email, isAdmin, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  const navItems = [
    { href: "/dashboard", label: "📊 Dashboard" },
    { href: "/profile",   label: "⚙️  Profile" },
  ];

  return (
    <aside className="w-64 shrink-0 bg-gray-900 border-r border-gray-800 flex flex-col p-5 sticky top-0 h-screen overflow-y-auto">
      {/* Logo + user */}
      <div className="mb-6">
        <Link href="/" className="flex items-center justify-center">
          <Image src="/vigilyx_logo.png" alt="Vigilyx" width={200} height={60} className="w-full h-auto" />
        </Link>
        <p className="text-xs text-gray-500 mt-0.5 truncate">{email}</p>
        {isAdmin && (
          <span className="mt-1.5 inline-block text-xs font-semibold px-2 py-0.5 rounded-full
                           bg-indigo-950 text-indigo-400 border border-indigo-800">
            Admin
          </span>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex flex-col gap-1 mb-5">
        {navItems.map(({ href, label }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={`text-sm px-3 py-2 rounded-lg transition-colors ${
                active
                  ? "bg-indigo-950 text-indigo-300 font-medium border border-indigo-800"
                  : "text-gray-400 hover:text-white hover:bg-gray-800"
              }`}
            >
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-gray-800 mb-5" />

      {/* Page-specific controls */}
      {children && <div className="flex-1 space-y-4">{children}</div>}
      {!children && <div className="flex-1" />}

      {/* Disconnect */}
      <button
        onClick={async () => { await logout(); router.push("/login"); }}
        className="w-full mt-4 rounded-lg border border-red-800 bg-transparent hover:bg-red-950
                   text-red-400 hover:text-red-300 text-sm font-medium px-4 py-2.5
                   transition-colors"
      >
        Disconnect
      </button>
    </aside>
  );
}
