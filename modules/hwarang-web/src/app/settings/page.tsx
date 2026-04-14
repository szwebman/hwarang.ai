"use client";

import { useState } from "react";
import { useTheme } from "@/components/providers/theme-provider";
import Link from "next/link";

export default function SettingsPage() {
  const { theme, toggleTheme } = useTheme();
  const [model, setModel] = useState("hwarang-small");
  const [temperature, setTemperature] = useState(0.7);
  const [maxTokens, setMaxTokens] = useState(2048);

  return (
    <div className="min-h-screen" style={{ background: "var(--background)" }}>
      <div className="max-w-2xl mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-2xl font-bold">Settings</h1>
          <Link
            href="/"
            className="text-sm px-4 py-2 rounded-lg border hover:bg-[var(--muted)] transition-colors"
            style={{ borderColor: "var(--border)" }}
          >
            Back to Chat
          </Link>
        </div>

        {/* Appearance */}
        <section className="mb-8">
          <h2 className="text-lg font-semibold mb-4">Appearance</h2>
          <div
            className="p-4 rounded-lg border"
            style={{ borderColor: "var(--border)" }}
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium text-sm">Theme</p>
                <p className="text-xs" style={{ color: "var(--muted-foreground)" }}>
                  Toggle between light and dark mode
                </p>
              </div>
              <button
                onClick={toggleTheme}
                className="px-4 py-2 rounded-lg border text-sm"
                style={{ borderColor: "var(--border)" }}
              >
                {theme === "light" ? "Dark Mode" : "Light Mode"}
              </button>
            </div>
          </div>
        </section>

        {/* Model Settings */}
        <section className="mb-8">
          <h2 className="text-lg font-semibold mb-4">Model</h2>
          <div
            className="p-4 rounded-lg border space-y-4"
            style={{ borderColor: "var(--border)" }}
          >
            <div>
              <label className="block text-sm font-medium mb-1">Default Model</label>
              <select
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border text-sm"
                style={{ borderColor: "var(--border)", background: "var(--background)" }}
              >
                <option value="hwarang-small">Hwarang Small (125M)</option>
                <option value="hwarang-medium">Hwarang Medium (350M)</option>
                <option value="hwarang-large">Hwarang Large (1.3B)</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">
                Temperature: {temperature}
              </label>
              <input
                type="range"
                min="0"
                max="2"
                step="0.1"
                value={temperature}
                onChange={(e) => setTemperature(parseFloat(e.target.value))}
                className="w-full"
              />
              <div className="flex justify-between text-xs" style={{ color: "var(--muted-foreground)" }}>
                <span>Precise (0)</span>
                <span>Creative (2)</span>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">
                Max Tokens: {maxTokens}
              </label>
              <input
                type="range"
                min="256"
                max="4096"
                step="256"
                value={maxTokens}
                onChange={(e) => setMaxTokens(parseInt(e.target.value))}
                className="w-full"
              />
            </div>
          </div>
        </section>

        {/* API */}
        <section className="mb-8">
          <h2 className="text-lg font-semibold mb-4">API</h2>
          <div
            className="p-4 rounded-lg border"
            style={{ borderColor: "var(--border)" }}
          >
            <p className="text-sm" style={{ color: "var(--muted-foreground)" }}>
              API endpoint: <code className="text-xs">http://localhost:8000</code>
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
