"""Calibration + lessons routes (ADR-0007 · ADR-0018 · ADR-0019).

POST /outcomes     — the frontend journal reports a graded, plan-sourced trade
                     (TP or SL). Idempotent on (symbol, closed_at). Each accepted
                     record recomputes the calibration state deterministically.
GET  /calibration  — the full recomputed state: per-seat reliability weights,
                     the refit blend weight, Brier scores of the blend vs its
                     halves, and the win-rate-per-confidence-bucket curve the
                     journal renders (NFR-7: confidence is a measured quantity).
POST /lessons      — a graded trade's post-mortem (tags + note) or a win record;
                     re-posting the same (symbol, closed_at) UPDATES the note.
GET  /lessons      — aggregated digest: per-variant performance, top failure
                     causes, recent post-mortems (also fed to the CIO's input).
"""

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.routes_market import require_auth
from app.desk.calibration import CalibrationState, CalibrationStore, OutcomeRecord
from app.desk.lessons import FAILURE_TAGS, LessonRecord, LessonsDigest, LessonsStore

router = APIRouter()


def _store(request: Request) -> CalibrationStore:
    return request.app.state.calibration_store


def _lessons(request: Request) -> LessonsStore:
    return request.app.state.lessons_store


@router.post("/outcomes", dependencies=[Depends(require_auth)])
async def record_outcome(outcome: OutcomeRecord, request: Request) -> dict:
    state, added = _store(request).record(outcome)
    return {
        "added": added,  # False = duplicate (symbol, closed_at) — not re-counted
        "n_outcomes": state.n_outcomes,
        "blend_w": state.blend_w,
        "blend_active": state.blend_active,
    }


@router.get(
    "/calibration", response_model=CalibrationState, dependencies=[Depends(require_auth)]
)
async def calibration(request: Request) -> CalibrationState:
    return _store(request).state()


@router.post("/lessons", dependencies=[Depends(require_auth)])
async def record_lesson(lesson: LessonRecord, request: Request) -> dict:
    bad = [t for t in lesson.tags if t not in FAILURE_TAGS]
    if bad:
        raise HTTPException(status_code=422, detail=f"unknown tags: {', '.join(bad)}")
    d = _lessons(request).record(lesson)
    return {"ok": True, "n_records": d.n_records}


@router.get(
    "/lessons", response_model=LessonsDigest, dependencies=[Depends(require_auth)]
)
async def lessons(request: Request) -> LessonsDigest:
    return _lessons(request).digest()


@router.get("/lessons/tags", dependencies=[Depends(require_auth)])
async def lesson_tags() -> dict:
    """The curated failure taxonomy (stable keys + bilingual labels) — the
    journal's post-mortem picker reads this, so taxonomy edits are config."""
    return {"tags": FAILURE_TAGS}
