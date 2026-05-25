"use client";

import { useEffect, useState } from "react";

// Slides in a loud red banner the instant the Merkle chain is broken (chaos
// tamper) and clears on restore — makes the integrity demo land on camera.
export function MerkleBanner() {
  const [broken, setBroken] = useState(false);

  useEffect(() => {
    let on = true;
    async function poll() {
      try {
        const r = await fetch("/api/backend/status");
        if (r.ok) {
          const d = await r.json();
          if (on) setBroken(d.merkleOk === false);
        }
      } catch {
        /* offline */
      }
    }
    poll();
    const id = setInterval(poll, 2000);
    return () => {
      on = false;
      clearInterval(id);
    };
  }, []);

  if (!broken) return null;
  return (
    <div className="absolute top-0 left-0 right-0 z-40 bg-red-600/90 text-white text-center
                    py-1.5 font-mono text-xs tracking-wide animate-pulse shadow-lg">
      ⚠ MERKLE CHAIN BROKEN — provenance integrity compromised. Restore to recover.
    </div>
  );
}
