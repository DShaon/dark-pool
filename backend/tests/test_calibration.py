"""Confidence recalibration tests (ADR-0018) — golden fixtures.

Every expected number is HAND-COMPUTED in a comment. These constants ARE the
recalibration contract: if a change breaks one, that is a money-risk change
and needs a new ADR, not a test edit.

λ = 0.977 → λ¹ = 0.977, λ² = 0.954529 (decay by outcome count, newest = 1).
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.desk.calibration import (
    CalibrationParams,
    CalibrationStore,
    OutcomeRecord,
    SeatVote,
    recalibrate,
)
from app.desk.confidence import compute_confidence
from app.desk.divergence import detect_divergence
from app.main import create_app
from tests.test_cio import aligned_panel, make_brief

T0 = datetime(2026, 7, 1, tzinfo=timezone.utc)


def outcome(
    i: int,
    outcome_: str,
    direction: str = "long",
    checklist: float = 0.7,
    agreement: float = 0.7,
    confidence: float = 0.7,
    seat_votes: dict | None = None,
) -> OutcomeRecord:
    return OutcomeRecord(
        symbol="TESTUSDT",
        direction=direction,  # type: ignore[arg-type]
        outcome=outcome_,  # type: ignore[arg-type]
        confidence=confidence,
        checklist=checklist,
        agreement=agreement,
        seat_votes={
            m: SeatVote(direction=v[0], conviction=v[1])
            for m, v in (seat_votes or {}).items()
        },
        closed_at=T0 + timedelta(hours=i),
    )


# ── empty state: everything neutral ───────────────────────────────────────


def test_empty_log_is_fully_neutral():
    s = recalibrate([])
    assert s.n_outcomes == 0 and s.eff_n == 0
    assert s.blend_w == 0.5 and s.blend_active is False
    # Beta(2,2) prior alone -> accuracy 0.5 -> weight exactly 1.0 for every seat
    assert all(seat.weight == 1.0 for seat in s.seats.values())
    assert s.brier_blended is None


# ── seat reliability: decay, shrinkage, clamps ─────────────────────────────


def test_seat_weights_decay_and_clamp_golden():
    votes = {"trend": ("long", 4), "contrarian": ("short", 3), "risk": ("no_trade", 2)}
    outs = [outcome(i, "tp", "long", seat_votes=votes) for i in range(3)]
    s = recalibrate(outs)

    # eff_n = 1 + 0.977 + 0.954529 = 2.931529
    assert s.seats["trend"].eff_n == pytest.approx(2.9315, abs=1e-4)
    # trend: all hits -> acc = (2.931529+2)/(2.931529+4) = 0.7115 -> raw weight
    # 1.4229 -> CLAMPED to 1.4 (a hot seat is capped, never dominant)
    assert s.seats["trend"].accuracy == pytest.approx(0.7115, abs=1e-4)
    assert s.seats["trend"].weight == 1.4
    # contrarian: dissented into 3 TPs -> 0 hits -> acc = 2/6.931529 = 0.2885
    # -> raw 0.5771 -> CLAMPED to 0.6 (a bad seat is dampened, never silenced)
    assert s.seats["contrarian"].accuracy == pytest.approx(0.2885, abs=1e-4)
    assert s.seats["contrarian"].weight == 0.6
    # risk abstained every time -> never scored -> neutral
    assert s.seats["risk"].eff_n == 0 and s.seats["risk"].weight == 1.0
    # derivatives never voted -> neutral
    assert s.seats["derivatives"].weight == 1.0


def test_dissenter_scores_a_hit_when_plan_loses():
    # Plan long -> SL. The contrarian who said short was RIGHT; trend was wrong.
    outs = [
        outcome(0, "sl", "long", seat_votes={"trend": ("long", 4), "contrarian": ("short", 3)})
    ]
    s = recalibrate(outs)
    # one miss:  acc = (0+2)/(1+4) = 0.4 -> weight 0.8
    assert s.seats["trend"].weight == 0.8
    # one hit:   acc = (1+2)/(1+4) = 0.6 -> weight 1.2
    assert s.seats["contrarian"].weight == 1.2


# ── blend refit: threshold, optimization, shrinkage ────────────────────────


def test_blend_frozen_below_min_effective_n():
    outs = [outcome(i, "tp", checklist=0.9, agreement=0.5) for i in range(3)]
    s = recalibrate(outs)
    assert s.blend_active is False and s.blend_w == 0.5  # 2.93 eff < 10


def test_blend_refit_golden_checklist_informative():
    # checklist is right (0.9 on winners, 0.1 on losers); agreement is noise
    # (0.5 always). Brier(w) = (0.5 - 0.4w)^2 for every record -> minimized at
    # the grid edge w_opt = 0.70.
    outs = [
        outcome(i, "tp" if i % 2 == 0 else "sl",
                checklist=0.9 if i % 2 == 0 else 0.1,
                agreement=0.5,
                confidence=0.7 if i % 2 == 0 else 0.3)
        for i in range(14)
    ]
    s = recalibrate(outs)
    assert s.blend_active is True
    # n_eff = (1 - 0.977^14)/0.023 = 12.0879
    assert s.eff_n == pytest.approx(12.0879, abs=1e-3)
    # shrunk: 0.5 + (0.7-0.5) * 12.0879/(12.0879+50) = 0.53894 -> 0.539
    assert s.blend_w == pytest.approx(0.539, abs=1e-3)
    # sanity: the checklist half really is the better predictor here
    assert s.brier_checklist < s.brier_agreement


def test_blend_never_leaves_its_clamp():
    # even with a perfectly informative agreement half, w floors at the
    # shrunk value of grid-min 0.30 -> always within [0.3, 0.7]
    outs = [
        outcome(i, "tp" if i % 2 == 0 else "sl",
                checklist=0.5,
                agreement=0.95 if i % 2 == 0 else 0.05)
        for i in range(60)
    ]
    s = recalibrate(outs)
    assert 0.3 <= s.blend_w <= 0.7
    assert s.blend_w < 0.5  # it learned agreement is better, direction correct


# ── calibration curve ──────────────────────────────────────────────────────


def test_curve_buckets_win_rates():
    outs = [
        outcome(0, "tp", confidence=0.85),
        outcome(1, "sl", confidence=0.82),
        outcome(2, "tp", confidence=0.65),
    ]
    s = recalibrate(outs)
    b8 = next(b for b in s.curve if b.lo == 0.8)
    assert b8.n == 2 and b8.wins == 1 and b8.win_rate == 0.5
    b6 = next(b for b in s.curve if b.lo == 0.6)
    assert b6.n == 1 and b6.win_rate == 1.0


# ── wiring into compute_confidence (golden, extends test_cio fixtures) ─────


def test_confidence_with_calibration_golden():
    brief, panel = make_brief(), aligned_panel()
    report = detect_divergence(panel, brief)
    params = CalibrationParams(
        blend_w=0.6, seat_weights={"trend": 1.4, "contrarian": 0.6}
    )
    c = compute_confidence(brief, "long", panel, report, params)
    # weighted convictions: trend 4x1.4=5.6 · contrarian 3x0.6=1.8 ·
    # derivatives 4x1.0=4 · risk 2x1.0=2 -> share 11.4/13.4 = 0.8507
    assert c.weighted_vote_share == pytest.approx(0.8507, abs=1e-4)
    # agreement = 0.5 + 0.5*0.850746 = 0.9254; checklist unchanged 0.7711
    assert c.agreement == pytest.approx(0.9254, abs=1e-4)
    assert c.checklist == 0.7711
    # value = 0.6*0.771075 + 0.4*0.925373 = 0.83279 -> 0.83
    assert c.value == 0.83
    assert c.calibrated is True and c.blend_w == 0.6
    assert c.seat_weights["trend"] == 1.4


def test_confidence_without_calibration_is_the_original_formula():
    brief, panel = make_brief(), aligned_panel()
    report = detect_divergence(panel, brief)
    c = compute_confidence(brief, "long", panel, report)  # no params
    assert c.value == 0.85  # the existing golden value, untouched
    assert c.calibrated is False and c.blend_w == 0.5 and c.seat_weights == {}


def test_neutral_params_report_uncalibrated():
    brief, panel = make_brief(), aligned_panel()
    report = detect_divergence(panel, brief)
    params = CalibrationParams(blend_w=0.5, seat_weights={m: 1.0 for m in ["trend"]})
    c = compute_confidence(brief, "long", panel, report, params)
    assert c.value == 0.85 and c.calibrated is False  # nothing actually moved


def test_seat_votes_ride_the_divergence_report():
    brief, panel = make_brief(), aligned_panel()
    report = detect_divergence(panel, brief)
    assert report.votes_by_seat["trend"].direction == "long"
    assert report.votes_by_seat["trend"].conviction == 4
    assert report.votes_by_seat["risk"].direction == "no_trade"


# ── store + routes ─────────────────────────────────────────────────────────


def test_store_idempotent_on_symbol_and_closed_at(tmp_path):
    store = CalibrationStore(tmp_path / "cal.json")
    o = outcome(0, "tp", seat_votes={"trend": ("long", 4)})
    s1, added1 = store.record(o)
    s2, added2 = store.record(o)  # a page-reload re-grade must not double-count
    assert added1 is True and added2 is False
    assert s1.n_outcomes == 1 and s2.n_outcomes == 1


def test_outcomes_route_records_and_calibration_route_reports(tmp_path):
    app = create_app()
    with TestClient(app) as client:
        app.state.calibration_store = CalibrationStore(tmp_path / "cal.json")
        body = {
            "symbol": "TESTUSDT",
            "direction": "long",
            "outcome": "tp",
            "confidence": 0.85,
            "checklist": 0.77,
            "agreement": 0.92,
            "seat_votes": {"trend": {"direction": "long", "conviction": 4}},
            "closed_at": "2026-07-10T12:00:00Z",
        }
        r = client.post("/outcomes", json=body)
        assert r.status_code == 200 and r.json()["added"] is True
        r2 = client.post("/outcomes", json=body)
        assert r2.json()["added"] is False  # idempotent

        cal = client.get("/calibration").json()
        assert cal["n_outcomes"] == 1
        assert cal["seats"]["trend"]["weight"] == 1.2  # (1+2)/(1+4)/0.5
        assert cal["blend_active"] is False  # far below 10 effective outcomes

        bad = {**body, "outcome": "open"}
        assert client.post("/outcomes", json=bad).status_code == 422
