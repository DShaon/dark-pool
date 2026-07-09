/** Thin header for non-desk pages (journal, settings) — wordmark, nav,
 *  clock. The full command bar (symbol form, palette) lives on the desk. */

import Clock from "@/components/Clock";
import DeskNav from "@/components/DeskNav";

export default function SiteHeader() {
  return (
    <header className="flex shrink-0 flex-wrap items-center justify-between gap-x-6 gap-y-2 border-b border-hair/80 px-4 py-3 sm:px-6">
      <div className="flex items-baseline gap-2.5">
        <span className="text-[13px] font-semibold tracking-[0.42em] text-hi">DARKPOOL</span>
        <span className="text-[12px] font-semibold tracking-[0.08em] text-gold">desk</span>
      </div>
      <DeskNav />
      <span className="hidden sm:inline">
        <Clock />
      </span>
    </header>
  );
}
