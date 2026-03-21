"use client";

import { useTheme } from "next-themes";
import { Monitor, Moon, Sun } from "lucide-react";

export function ThemeSection() {
  const { theme, setTheme } = useTheme();

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row gap-3">
        <button
          onClick={() => setTheme("light")}
          className={`flex items-center justify-center gap-2 px-4 py-3 rounded-lg border text-sm font-medium transition-colors ${
            theme === "light"
              ? "bg-iv-green text-black border-iv-green"
              : "bg-iv-surface text-iv-muted border-iv-border hover:border-iv-green/50"
          }`}
        >
          <Sun size={16} /> Light
        </button>
        <button
          onClick={() => setTheme("dark")}
          className={`flex items-center justify-center gap-2 px-4 py-3 rounded-lg border text-sm font-medium transition-colors ${
            theme === "dark"
              ? "bg-iv-green text-black border-iv-green"
              : "bg-iv-surface text-iv-muted border-iv-border hover:border-iv-green/50"
          }`}
        >
          <Moon size={16} /> Dark
        </button>
        <button
          onClick={() => setTheme("system")}
          className={`flex items-center justify-center gap-2 px-4 py-3 rounded-lg border text-sm font-medium transition-colors ${
            theme === "system"
              ? "bg-iv-green text-black border-iv-green"
              : "bg-iv-surface text-iv-muted border-iv-border hover:border-iv-green/50"
          }`}
        >
          <Monitor size={16} /> System
        </button>
      </div>
      <p className="text-xs text-iv-muted">
        System mode automatically adapts the theme to your device's operating system preferences.
      </p>
    </div>
  );
}
