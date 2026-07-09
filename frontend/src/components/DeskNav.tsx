"use client";

/** Desk navigation — desk / journal / settings. Active route reads bright;
 *  the rest stay dim chrome until hovered. */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { memo } from "react";

const LINKS: Array<[href: string, label: string]> = [
  ["/", "desk"],
  ["/journal", "journal"],
  ["/settings", "settings"],
];

function DeskNav() {
  const path = usePathname();
  return (
    <nav className="flex items-center gap-4">
      {LINKS.map(([href, label]) => (
        <Link
          key={href}
          href={href}
          className={`text-[11px] font-medium uppercase tracking-[0.16em] transition-colors duration-200 ${
            path === href ? "text-hi" : "text-dim hover:text-mid"
          }`}
        >
          {label}
        </Link>
      ))}
    </nav>
  );
}

export default memo(DeskNav);
