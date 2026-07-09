"use client";

/** Ticking clock — displays Bangladesh time (Asia/Dhaka, UTC+6).
 *  Storage/transport stays UTC; only the display converts (invariant 3). */

import { memo, useEffect, useState } from "react";

import { dhakaTime } from "@/lib/time";

function Clock() {
  const [now, setNow] = useState<string>("");
  useEffect(() => {
    const tick = () => setNow(dhakaTime());
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <span className="font-mono text-xs tabular-nums text-dim" suppressHydrationWarning>
      {now} <span className="font-bn">ঢাকা</span>
    </span>
  );
}

export default memo(Clock);
