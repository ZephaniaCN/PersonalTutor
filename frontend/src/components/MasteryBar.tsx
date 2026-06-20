"use client";

/**
 * A compact mastery bar: shows a 0..1 value with a color band and level label.
 * Reused across profile, roadmap, and quiz screens so mastery reads the same
 * everywhere.
 *
 * Kept as a client component only because it reads a CSS variable at render —
 * it has no interactivity of its own.
 */

const LEVELS: { threshold: number; label: string; color: string }[] = [
  { threshold: 0.85, label: "精通", color: "#3fb950" },
  { threshold: 0.7, label: "熟练", color: "#56d364" },
  { threshold: 0.4, label: "入门", color: "#d29922" },
  { threshold: 0.0, label: "未入门", color: "#f85149" },
];

export function levelOf(mastery: number) {
  return LEVELS.find((l) => mastery >= l.threshold) ?? LEVELS[LEVELS.length - 1];
}

export function MasteryBar({ mastery, showLabel = true }: { mastery: number; showLabel?: boolean }) {
  const lvl = levelOf(mastery);
  const pct = Math.round(mastery * 100);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 120 }}>
      <div
        style={{
          flex: 1,
          height: 8,
          background: "var(--border)",
          borderRadius: 4,
          overflow: "hidden",
        }}
      >
        <div
          style={{ width: `${pct}%`, height: "100%", background: lvl.color, transition: "width .3s" }}
        />
      </div>
      {showLabel && (
        <span style={{ fontSize: "0.8rem", color: "var(--muted)", minWidth: 72 }}>
          {lvl.label} {pct}%
        </span>
      )}
    </div>
  );
}
