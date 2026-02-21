"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email, password);
      router.push("/dashboard");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <img src="/vigilyx_logo.png" alt="Vigilyx" className="h-10 w-auto mx-auto mb-4" />
          <p className="text-gray-400 mt-1 text-sm">Sign in to your account</p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="bg-gray-900 border border-gray-800 rounded-2xl p-8 space-y-5"
        >
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1.5">
              Email
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="acme@demo.com"
              className="w-full rounded-lg bg-gray-800 border border-gray-700 px-4 py-2.5
                         text-white placeholder-gray-500 focus:outline-none focus:ring-2
                         focus:ring-indigo-500 focus:border-transparent transition"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1.5">
              Password
            </label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full rounded-lg bg-gray-800 border border-gray-700 px-4 py-2.5
                         text-white placeholder-gray-500 focus:outline-none focus:ring-2
                         focus:ring-indigo-500 focus:border-transparent transition"
            />
          </div>

          {error && (
            <p className="text-sm text-red-400 bg-red-950 border border-red-800 rounded-lg px-4 py-2.5">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50
                       disabled:cursor-not-allowed px-4 py-2.5 text-white font-semibold
                       transition-colors"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <div className="mt-6 space-y-1.5 text-center text-xs text-gray-500">
          <p>
            <span className="text-gray-400">acme@demo.com</span> or{" "}
            <span className="text-gray-400">globex@demo.com</span> — password:{" "}
            <span className="text-gray-400">demo1234</span>
          </p>
          <p>
            <span className="text-indigo-400 font-medium">admin@demo.com</span> — password:{" "}
            <span className="text-gray-400">admin1234</span>{" "}
            <span className="text-indigo-500">(all companies)</span>
          </p>
        </div>
      </div>
    </div>
  );
}
