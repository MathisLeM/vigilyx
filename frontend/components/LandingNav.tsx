"use client";

import Link from "next/link";
import Image from "next/image";
import { useAuth } from "@/lib/auth";

export default function LandingNav() {
  const { isAuthenticated } = useAuth();

  return (
    <header className="fixed top-0 left-0 right-0 z-50 border-b border-white/5 bg-gray-950/80 backdrop-blur-md">
      <div className="max-w-6xl mx-auto px-6 py-2 relative flex items-center justify-center">

        {/* Nav links — absolute left */}
        <nav className="absolute left-6 hidden md:flex items-center gap-6 text-sm text-gray-400">
          <a href="#features" className="hover:text-white transition-colors">Features</a>
          <a href="#how-it-works" className="hover:text-white transition-colors">How it works</a>
        </nav>

        {/* Logo — centered, cropped 15% top+bottom (overflow-hidden on wrapper) */}
        <Link href="/" className="overflow-hidden h-32 flex items-center justify-center">
          <Image src="/vigilyx_logo.png" alt="Vigilyx" width={320} height={320} className="h-80 w-auto block shrink-0" />
        </Link>

        {/* CTA — absolute right */}
        <div className="absolute right-6 flex items-center gap-3">
          {isAuthenticated ? (
            <Link
              href="/dashboard"
              className="bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold
                         px-4 py-2 rounded-lg transition-colors"
            >
              Go to Dashboard →
            </Link>
          ) : (
            <>
              <Link
                href="/login"
                className="text-sm text-gray-400 hover:text-white transition-colors"
              >
                Sign in
              </Link>
              <Link
                href="/login"
                className="bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold
                           px-4 py-2 rounded-lg transition-colors"
              >
                Get started
              </Link>
            </>
          )}
        </div>

      </div>
    </header>
  );
}
