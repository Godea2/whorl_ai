"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function ResetPasswordPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [ready, setReady] = useState(false);
  const [sessionMissing, setSessionMissing] = useState(false);

  useEffect(() => {
    const supabase = createClient();
    let cancelled = false;

    async function ensureRecoverySession() {
      const {
        data: { session },
      } = await supabase.auth.getSession();

      if (cancelled) return;

      if (session) {
        setReady(true);
        return;
      }

      // Older email templates may land with hash tokens; wait briefly for client parse.
      await new Promise((r) => setTimeout(r, 800));
      const {
        data: { session: retry },
      } = await supabase.auth.getSession();

      if (cancelled) return;

      if (retry) {
        setReady(true);
      } else {
        setSessionMissing(true);
      }
    }

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === "PASSWORD_RECOVERY" || (session && event === "SIGNED_IN")) {
        setReady(true);
        setSessionMissing(false);
      }
    });

    void ensureRecoverySession();

    return () => {
      cancelled = true;
      subscription.unsubscribe();
    };
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setMessage("");

    if (password.length < 6) {
      setError("Password must be at least 6 characters.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);
    const supabase = createClient();
    const { error: updateError } = await supabase.auth.updateUser({ password });
    setLoading(false);

    if (updateError) {
      setError(updateError.message);
      return;
    }

    setMessage("Password updated. You can sign in with your new password.");
    await supabase.auth.signOut();
    router.push("/login");
    router.refresh();
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Choose a new password</CardTitle>
          <CardDescription>Enter and confirm your new password</CardDescription>
        </CardHeader>

        {sessionMissing ? (
          <div className="space-y-4">
            <p className="text-sm text-red-400">
              This reset link is invalid or has expired. Request a new one.
            </p>
            <Link href="/forgot-password" className="text-sm text-blue-400 hover:underline">
              Send a new reset link
            </Link>
          </div>
        ) : !ready ? (
          <p className="text-sm text-slate-400">Verifying reset link…</p>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <Input
              type="password"
              placeholder="New password (min 6 chars)"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={6}
              autoComplete="new-password"
            />
            <Input
              type="password"
              placeholder="Confirm new password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              minLength={6}
              autoComplete="new-password"
            />
            {error && <p className="text-sm text-red-400">{error}</p>}
            {message && <p className="text-sm text-slate-400">{message}</p>}
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "Saving…" : "Save new password"}
            </Button>
          </form>
        )}

        <p className="mt-4 text-center text-sm text-slate-400">
          <Link href="/login" className="text-blue-400 hover:underline">
            Back to sign in
          </Link>
        </p>
      </Card>
    </div>
  );
}
