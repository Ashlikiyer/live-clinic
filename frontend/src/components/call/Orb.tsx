/** Mia's orb: a soft sphere that breathes, with rings that ripple out while she talks or listens. */

export type OrbMode = "speak" | "listen" | "idle" | "hero";

export function Orb({ size, mode, label }: { size: number; mode: OrbMode; label?: string }) {
  const speaking = mode === "speak";
  const rippling = speaking || mode === "listen" || mode === "hero";
  const ring = (delay: number) => (
    <span
      className="absolute inset-0 rounded-full border-[1.5px]"
      style={{
        borderColor: "oklch(0.7 0.12 15 / .5)",
        animation: rippling ? `lcd-ring ${speaking ? 1.4 : 2.8}s ease-out ${delay}s infinite` : "none",
        opacity: rippling ? 1 : 0,
      }}
    />
  );
  return (
    <div
      className="relative flex-none"
      style={{ width: size, height: size }}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      {ring(0)}
      {ring(speaking ? 0.7 : 1.4)}
      <span
        className="absolute rounded-full"
        style={{
          inset: size * 0.17,
          background:
            "radial-gradient(circle at 34% 28%, #fff 0%, oklch(0.88 0.05 15) 22%, oklch(0.55 0.08 330) 60%, #18181b 100%)",
          boxShadow: "0 18px 40px -14px oklch(0.45 0.12 15 / .55), inset 0 -8px 20px rgba(0,0,0,.35)",
          animation: speaking ? "lcd-breathe .8s ease-in-out infinite" : "lcd-breathe 4.5s ease-in-out infinite",
        }}
      />
    </div>
  );
}

/** Seven little bars that dance while the microphone hears the caller. */
export function MicBars({ on }: { on: boolean }) {
  return (
    <span className="flex h-3.5 items-center gap-[3px]" aria-hidden>
      {[0, 1, 2, 3, 4, 5, 6].map((i) => (
        <span
          key={i}
          className={`h-3.5 w-[3px] rounded-sm ${on ? "bg-ink" : "bg-[#d9d9d5]"}`}
          style={{
            transform: "scaleY(.25)",
            animation: on
              ? `lcd-bar ${0.32 + ((i * 37) % 5) * 0.07}s ease-in-out ${i * 0.05}s infinite alternate`
              : "none",
          }}
        />
      ))}
    </span>
  );
}
