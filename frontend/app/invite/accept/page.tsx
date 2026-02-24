"use client";

import { useEffect, useState, FormEvent, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { validateInviteToken, acceptInvitation, AcceptTokenInfo } from "@/lib/api";
import { useAuth } from "@/lib/auth";

function AcceptForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { refetchUser } = useAuth();
  const token = searchParams.get("token") ?? "";

  const [tokenInfo, setTokenInfo] = useState<AcceptTokenInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [tokenError, setTokenError] = useState<string | null>(null);

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setTokenError("No invitation token found in this link.");
      setLoading(false);
      return;
    }
    validateInviteToken(token)
      .then((info) => {
        setTokenInfo(info);
        if (!info.valid) {
          if (info.expired) setTokenError("This invitation has expired.");
          else if (info.already_accepted) setTokenError("This invitation has already been accepted.");
          else setTokenError("This invitation link is invalid.");
        }
      })
      .catch(() => setTokenError("Failed to validate invitation. The link may be invalid or expired."))
      .finally(() => setLoading(false));
  }, [token]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (password !== confirm) {
      setSubmitError("Passwords do not match.");
      return;
    }
    if (password.length < 8) {
      setSubmitError("Password must be at least 8 characters.");
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      await acceptInvitation(token, password);
      await refetchUser();
      router.replace("/dashboard");
    } catch (err: unknown) {
      setSubmitError(err instanceof Error ? err.message : "Registration failed");
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-8 space-y-6">
          <div className="space-y-1">
            <h1 className="text-xl font-bold text-white">Accept invitation</h1>
            {!loading && tokenInfo?.valid && (
              <p className="text-sm text-gray-400">
                You&apos;ve been invited to join{" "}
                <span className="text-white font-medium">{tokenInfo.tenant_name}</span>
              </p>
            )}
          </div>

          {loading && (
            <p className="text-sm text-gray-500">Validating invitation…</p>
          )}

          {tokenError && (
            <div className="bg-red-950 border border-red-800 rounded-lg px-4 py-3">
              <p className="text-sm text-red-400">{tokenError}</p>
              <a href="/login" className="text-xs text-indigo-400 hover:text-indigo-300 mt-2 inline-block">
                Go to login
              </a>
            </div>
          )}

          {!loading && tokenInfo?.valid && (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-medium text-gray-400 uppercase tracking-wide">Email</label>
                <p className="text-sm text-gray-300 bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5">
                  {tokenInfo.email}
                </p>
              </div>

              <div className="space-y-1">
                <label htmlFor="password" className="text-xs font-medium text-gray-400 uppercase tracking-wide">
                  Choose a password
                </label>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={8}
                  placeholder="Minimum 8 characters"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5
                             text-sm text-white placeholder-gray-500
                             focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                />
              </div>

              <div className="space-y-1">
                <label htmlFor="confirm" className="text-xs font-medium text-gray-400 uppercase tracking-wide">
                  Confirm password
                </label>
                <input
                  id="confirm"
                  type="password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  required
                  placeholder="Repeat your password"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5
                             text-sm text-white placeholder-gray-500
                             focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                />
              </div>

              {submitError && (
                <p className="text-sm text-red-400 bg-red-950 border border-red-800 rounded-lg px-4 py-2">
                  {submitError}
                </p>
              )}

              <button
                type="submit"
                disabled={submitting || !password || !confirm}
                className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50
                           disabled:cursor-not-allowed text-white text-sm font-semibold
                           rounded-lg px-4 py-2.5 transition-colors"
              >
                {submitting ? "Creating account…" : "Create account & sign in"}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}

export default function AcceptPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <p className="text-gray-500 text-sm">Loading…</p>
      </div>
    }>
      <AcceptForm />
    </Suspense>
  );
}
