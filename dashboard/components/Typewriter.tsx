"use client";

import { useEffect, useState } from "react";

// Reveals text progressively (with a blinking cursor) so answers look like
// live reasoning streaming in. Chunk size scales with length so long answers
// still finish quickly.
export function Typewriter({ text, speed = 16 }: { text: string; speed?: number }) {
  const [n, setN] = useState(0);

  useEffect(() => {
    setN(0);
    if (!text) return;
    const step = Math.max(1, Math.ceil(text.length / 180));
    const id = setInterval(() => {
      setN((x) => {
        if (x >= text.length) {
          clearInterval(id);
          return x;
        }
        return x + step;
      });
    }, speed);
    return () => clearInterval(id);
  }, [text, speed]);

  return (
    <span>
      {text.slice(0, n)}
      {n < text.length && <span className="animate-pulse text-purple-300">▋</span>}
    </span>
  );
}
