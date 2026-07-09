"use client";

/** Sample-data badge — the honest marker on surfaces whose numbers are
 *  placeholder-scaled off the live price (trade setups, consensus map, tape)
 *  until the real analyst desk wires in at P2. It is hoverable: the tooltip
 *  explains, in Bengali + English, exactly what "sample" means and when real
 *  data arrives — so the label informs instead of just looking unfinished.
 *
 *  This replaces the bare "DEMO" tag (user asked why it was there).
 */

import Term from "@/components/Term";

export default function SampleTag() {
  return (
    <Term k="SAMPLE" bare className="demo-tag whitespace-nowrap">
      <span className="font-bn">নমুনা</span> · SAMPLE
    </Term>
  );
}
