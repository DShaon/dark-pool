/** Display-time helpers — the desk DISPLAYS Bangladesh time (Asia/Dhaka,
 *  UTC+6). All stored/transported timestamps stay UTC (CLAUDE.md invariant
 *  3); conversion happens only here, at the render boundary.
 */

const dhakaClock = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Dhaka",
  hour12: false,
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

/** "HH:MM:SS" in Bangladesh time. */
export function dhakaTime(d: Date | string = new Date()): string {
  return dhakaClock.format(typeof d === "string" ? new Date(d) : d);
}
