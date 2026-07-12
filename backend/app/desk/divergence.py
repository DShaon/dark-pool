"""Divergence detector (§B5, ADR-0015) — pure code, no LLM, fully unit-tested.

Classifies the surviving analyst panel into consensus_state ∈
{aligned, split, contested} from three deterministic signals:

  1. direction agreement  — long/short/no_trade votes, conviction-weighted;
  2. level clustering     — do the agreeing entries sit within one ATR band
                            (stops within 1.5x — mandates legitimately trail
                            stops differently), anchored on the 1h ATR
                            (intraday anchor; 15m then 4h as fallback);
  3. conviction spread    — max−min conviction among the agreeing seats.

Rules (ordered; every classification appends a human-readable note — the
audit trail):

  * no directional votes at all      -> plurality no_trade, ALIGNED
                                        (the whole desk standing aside IS
                                        consensus, not absence of one);
  * long AND short both present      -> CONTESTED if both sides carry a
                                        conviction >= 3 voice, else SPLIT;
                                        plurality = higher conviction-weighted
                                        side (tie -> no_trade / contested);
  * one direction only               -> ALIGNED iff >= 2 seats voted it,
                                        at most 1 abstention (a no_trade risk
                                        officer is mandate-expected), entries
                                        cluster (unknown data passes — missing
                                        ATR must not manufacture dissent), and
                                        conviction spread <= 2; else SPLIT.
  * fewer than 2 survivors           -> SPLIT (one voice is never consensus).

Unknown clustering (no ATR, or < 2 zoned entries) is reported as None and
treated as non-blocking — only a POSITIVE scatter finding breaks alignment.
"""

from decimal import Decimal

from app.models.analyst import AnalystThesis
from app.models.brief import MarketBrief
from app.models.tradeplan import Direction, DivergenceReport, SeatVoteOut

# Intraday anchor first (§B5: 15m/1h/4h core; 1h is the desk's reference TF).
ATR_TF_PRIORITY = ("1h", "15m", "4h")
ENTRY_CLUSTER_ATR = Decimal("1.0")
STOP_CLUSTER_ATR = Decimal("1.5")
CONTESTED_MIN_CONVICTION = 3
ALIGNED_MAX_SPREAD = 2
ALIGNED_MIN_VOTES = 2
ALIGNED_MAX_ABSTAIN = 1


def anchor_atr(brief: MarketBrief) -> Decimal | None:
    """The ATR the desk clusters levels against (1h -> 15m -> 4h)."""
    for tf in ATR_TF_PRIORITY:
        tfa = brief.timeframes.get(tf)
        if tfa is not None and tfa.indicators.atr14 is not None:
            return Decimal(str(tfa.indicators.atr14))
    return None


def _spread_within(values: list[Decimal], band: Decimal) -> bool:
    return max(values) - min(values) <= band


def _cluster(
    theses: list[AnalystThesis], direction: str, atr: Decimal | None
) -> tuple[bool | None, bool | None]:
    """(entry_cluster, stop_cluster) for the seats voting `direction`.
    None = not enough data to judge (never counted as dissent)."""
    if atr is None or atr <= 0:
        return None, None
    entries = [
        (t.read.entry_zone.low + t.read.entry_zone.high) / 2
        for t in theses
        if t.read.direction == direction and t.read.entry_zone is not None
    ]
    stops = [
        t.read.stop_loss
        for t in theses
        if t.read.direction == direction and t.read.stop_loss is not None
    ]
    entry_cluster = (
        _spread_within(entries, ENTRY_CLUSTER_ATR * atr) if len(entries) >= 2 else None
    )
    stop_cluster = (
        _spread_within(stops, STOP_CLUSTER_ATR * atr) if len(stops) >= 2 else None
    )
    return entry_cluster, stop_cluster


def detect_divergence(
    theses: list[AnalystThesis], brief: MarketBrief
) -> DivergenceReport:
    votes: dict[str, int] = {"long": 0, "short": 0, "no_trade": 0}
    weighted: dict[str, int] = {"long": 0, "short": 0, "no_trade": 0}
    # Raw per-seat votes ride the report so graded outcomes can score seat
    # reliability later (ADR-0018) and the plan's provenance stays auditable.
    by_seat: dict[str, SeatVoteOut] = {}
    for t in theses:
        votes[t.read.direction] += 1
        weighted[t.read.direction] += t.read.conviction
        by_seat[t.mandate] = SeatVoteOut(
            direction=t.read.direction, conviction=t.read.conviction
        )

    convictions = [t.read.conviction for t in theses]
    spread = (max(convictions) - min(convictions)) if convictions else 0
    notes: list[str] = []
    atr = anchor_atr(brief)

    directional = votes["long"] + votes["short"]

    # -- whole desk stands aside ------------------------------------------
    if directional == 0:
        notes.append("no directional votes — the desk stands aside as one")
        return DivergenceReport(
            consensus_state="aligned" if len(theses) >= 2 else "split",
            plurality_direction="no_trade",
            votes=votes,
            conviction_weighted=weighted,
            votes_by_seat=by_seat,
            conviction_spread=spread,
            notes=notes
            if len(theses) >= 2
            else notes + ["fewer than 2 survivors — one voice is not consensus"],
        )

    # -- opposed directional reads ----------------------------------------
    if votes["long"] > 0 and votes["short"] > 0:
        if weighted["long"] > weighted["short"]:
            plurality: Direction = "long"
        elif weighted["short"] > weighted["long"]:
            plurality = "short"
        else:
            plurality = "no_trade"
            notes.append("conviction-weighted tie between long and short")

        max_long = max(t.read.conviction for t in theses if t.read.direction == "long")
        max_short = max(
            t.read.conviction for t in theses if t.read.direction == "short"
        )
        entry_cluster, stop_cluster = _cluster(theses, plurality, atr) if plurality != "no_trade" else (None, None)

        if min(max_long, max_short) >= CONTESTED_MIN_CONVICTION:
            notes.append(
                f"opposing reads both confident (long max {max_long}, short max {max_short})"
            )
            state = "contested"
        else:
            notes.append("opposition exists but one side is low-conviction")
            state = "split"
        return DivergenceReport(
            consensus_state=state,
            plurality_direction=plurality,
            votes=votes,
            conviction_weighted=weighted,
            votes_by_seat=by_seat,
            entry_cluster=entry_cluster,
            stop_cluster=stop_cluster,
            conviction_spread=spread,
            notes=notes,
        )

    # -- one direction only -------------------------------------------------
    plurality = "long" if votes["long"] > 0 else "short"
    entry_cluster, stop_cluster = _cluster(theses, plurality, atr)
    plurality_convictions = [
        t.read.conviction for t in theses if t.read.direction == plurality
    ]
    plurality_spread = max(plurality_convictions) - min(plurality_convictions)

    aligned = True
    if len(theses) < 2:
        aligned = False
        notes.append("fewer than 2 survivors — one voice is not consensus")
    if votes[plurality] < ALIGNED_MIN_VOTES:
        aligned = False
        notes.append(f"only {votes[plurality]} seat(s) voted {plurality}")
    if votes["no_trade"] > ALIGNED_MAX_ABSTAIN:
        aligned = False
        notes.append(f"{votes['no_trade']} seats abstained (max {ALIGNED_MAX_ABSTAIN} for aligned)")
    if entry_cluster is False:  # only a POSITIVE scatter finding blocks
        aligned = False
        notes.append("entries scatter beyond 1.0x ATR — levels do not cluster")
    if plurality_spread > ALIGNED_MAX_SPREAD:
        aligned = False
        notes.append(f"conviction spread {plurality_spread} > {ALIGNED_MAX_SPREAD} among agreeing seats")
    if aligned:
        notes.append(
            f"{votes[plurality]} seats {plurality}, {votes['no_trade']} abstaining, levels cluster"
        )

    return DivergenceReport(
        consensus_state="aligned" if aligned else "split",
        plurality_direction=plurality,
        votes=votes,
        conviction_weighted=weighted,
        votes_by_seat=by_seat,
        entry_cluster=entry_cluster,
        stop_cluster=stop_cluster,
        conviction_spread=spread,
        notes=notes,
    )


__all__ = ["detect_divergence", "anchor_atr"]
