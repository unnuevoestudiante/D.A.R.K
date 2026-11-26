import { useEffect, useRef, useState } from "react";
import type { DarkState } from "@/lib/dark-state";

const BAR_COUNT = 5;
const BASE = [0.62, 0.9, 0.55, 0.48, 0.7];

/** Cinco barras tipo cápsula. Reaccionan al estado y al nivel de voz. */
export function DarkWave({
  state,
  level,
  size = 1,
}: {
  state: DarkState;
  level: number;
  size?: number;
}) {
  const [heights, setHeights] = useState<number[]>(BASE);
  const frame = useRef<number>(0);
  const levelRef = useRef(level);
  const stateRef = useRef(state);
  levelRef.current = level;
  stateRef.current = state;

  useEffect(() => {
    const start = performance.now();

    const tick = (now: number) => {
      const t = (now - start) / 1000;
      const s = stateRef.current;
      const loud = levelRef.current;

      const phaseSpeed =
        s === "thinking"
          ? 2.2
          : s === "speaking"
            ? 4.4
            : s === "transcribing"
              ? 3.0
              : 1.4;

      const next = BASE.map((base, i) => {
        const phase = t * phaseSpeed + i * 0.7;

        if (s === "idle") return 0.28 + Math.sin(phase) * 0.04;

        if (s === "listening") {
          const wave = 0.5 + Math.sin(phase) * 0.12;
          return Math.min(1, wave + loud * 0.55 * base);
        }

        if (s === "transcribing") {
          const ripple = 0.42 + Math.sin(phase * 1.6 + i * 1.1) * 0.24;
          return Math.max(0.18, ripple);
        }

        if (s === "thinking")
          return 0.35 + Math.abs(Math.sin(phase)) * 0.5 * base;

        return Math.min(
          1,
          base * (0.55 + Math.abs(Math.sin(phase)) * 0.6) + loud * 0.35,
        );
      });

      setHeights((prev) => prev.map((h, i) => h + ((next[i] ?? h) - h) * 0.22));
      frame.current = requestAnimationFrame(tick);
    };

    frame.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame.current);
  }, []);

  const trackHeight = 200 * size;
  const barWidth = 44 * size;

  return (
    <div
      className="flex items-center justify-center gap-4"
      style={{ height: trackHeight }}
      aria-hidden
    >
      {Array.from({ length: BAR_COUNT }).map((_, i) => (
        <div
          key={i}
          className="flex items-center"
          style={{ height: trackHeight }}
        >
          <div
            className="rounded-full transition-[height] duration-100 ease-out"
            style={{
              width: barWidth,
              height: Math.max(barWidth, (heights[i] ?? 0.3) * trackHeight),
              transform: `translateY(${(i % 2 === 0 ? -1 : 1) * 10 * size}px)`,
              background:
                "linear-gradient(180deg, oklch(0.72 0.24 293) 0%, oklch(0.58 0.26 291) 100%)",
              boxShadow:
                "0 0 20px oklch(0.62 0.28 291 / 0.35), 0 0 40px oklch(0.62 0.28 291 / 0.15)",
            }}
          />
        </div>
      ))}
    </div>
  );
}
