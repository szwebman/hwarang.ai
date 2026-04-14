"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");

    // TODO: Implement with NextAuth
    try {
      // Placeholder login logic
      console.log("Login:", email);
    } catch {
      setError("Login failed. Please try again.");
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--muted)" }}>
      <div
        className="w-full max-w-md p-8 rounded-2xl border"
        style={{ background: "var(--background)", borderColor: "var(--border)" }}
      >
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold">Hwarang AI</h1>
          <p className="mt-2 text-sm" style={{ color: "var(--muted-foreground)" }}>
            Sign in to your account
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full px-3 py-2 rounded-lg border text-sm"
              style={{ borderColor: "var(--border)", background: "var(--background)" }}
              placeholder="you@example.com"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full px-3 py-2 rounded-lg border text-sm"
              style={{ borderColor: "var(--border)", background: "var(--background)" }}
              placeholder="Enter your password"
            />
          </div>

          {error && (
            <p className="text-sm" style={{ color: "var(--destructive)" }}>{error}</p>
          )}

          <button
            type="submit"
            className="w-full py-2.5 rounded-lg text-sm font-medium transition-colors"
            style={{ background: "var(--primary)", color: "var(--primary-foreground)" }}
          >
            Sign In
          </button>
        </form>

        <p className="mt-6 text-center text-sm" style={{ color: "var(--muted-foreground)" }}>
          Don&apos;t have an account?{" "}
          <Link href="/register" className="underline" style={{ color: "var(--primary)" }}>
            Sign up
          </Link>
        </p>
      </div>
    </div>
  );
}
