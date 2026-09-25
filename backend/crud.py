"""
crud.py — Database helpers for the self-learning agent.
"""
import json
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import Submission, MistakePattern, LearnerProfile


# ─── Learner Profile ────────────────────────────────────────────────────────

async def get_or_create_profile(db: AsyncSession, session_id: str) -> LearnerProfile:
    result = await db.execute(
        select(LearnerProfile).where(LearnerProfile.session_id == session_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        profile = LearnerProfile(session_id=session_id)
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
    return profile


async def profile_to_dict(profile: LearnerProfile) -> dict:
    top_mistakes = []
    try:
        top_mistakes = json.loads(profile.top_mistakes) if profile.top_mistakes else []
    except (json.JSONDecodeError, TypeError):
        pass
    return {
        "session_id": profile.session_id,
        "current_difficulty": profile.current_difficulty,
        "total_submissions": profile.total_submissions,
        "avg_score": round(profile.avg_score, 1),
        "top_mistakes": top_mistakes,
        "preferred_language": profile.preferred_language,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


def lean_profile_for_llm(profile_dict: dict) -> dict:
    """Return only the fields the LLM actually uses — keeps token count minimal."""
    return {
        "session_id": profile_dict.get("session_id", ""),
        "current_difficulty": profile_dict.get("current_difficulty", 1),
        "total_submissions": profile_dict.get("total_submissions", 0),
        "avg_score": profile_dict.get("avg_score", 0.0),
        "top_mistakes": profile_dict.get("top_mistakes", [])[:3],
        "preferred_language": profile_dict.get("preferred_language", "python"),
    }


async def update_profile_after_submission(
    db: AsyncSession,
    profile: LearnerProfile,
    score: float,
    language: str,
) -> LearnerProfile:
    """Recalculate rolling average score and adapt difficulty."""
    n = profile.total_submissions
    new_avg = (profile.avg_score * n + score) / (n + 1)
    profile.total_submissions = n + 1
    profile.avg_score = new_avg
    profile.preferred_language = language
    profile.updated_at = datetime.now(timezone.utc)

    # Adapt difficulty: if avg score > 80 for 3+ subs → increase; if < 40 → decrease
    if n + 1 >= 3:
        if new_avg >= 80 and profile.current_difficulty < 5:
            profile.current_difficulty += 1
        elif new_avg < 40 and profile.current_difficulty > 1:
            profile.current_difficulty -= 1

    # Refresh top_mistakes from MistakePattern table
    result = await db.execute(
        select(MistakePattern)
        .where(MistakePattern.session_id == profile.session_id)
        .order_by(MistakePattern.count.desc())
        .limit(8)
    )
    top = result.scalars().all()
    profile.top_mistakes = json.dumps([p.tag for p in top])

    await db.commit()
    await db.refresh(profile)
    return profile


# ─── Mistake Patterns ───────────────────────────────────────────────────────

async def record_mistakes(db: AsyncSession, session_id: str, tags: list[str]):
    """Upsert mistake tag counts for the session."""
    for tag in tags:
        if not tag:
            continue
        result = await db.execute(
            select(MistakePattern).where(
                MistakePattern.session_id == session_id,
                MistakePattern.tag == tag,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.count += 1
            existing.last_seen = datetime.now(timezone.utc)
        else:
            db.add(MistakePattern(session_id=session_id, tag=tag, count=1))
    await db.commit()


async def get_mistake_patterns(db: AsyncSession, session_id: str) -> list[dict]:
    result = await db.execute(
        select(MistakePattern)
        .where(MistakePattern.session_id == session_id)
        .order_by(MistakePattern.count.desc())
    )
    rows = result.scalars().all()
    return [
        {
            "tag": r.tag,
            "count": r.count,
            "last_seen": r.last_seen.isoformat() if r.last_seen else None,
        }
        for r in rows
    ]


# ─── Submissions ─────────────────────────────────────────────────────────────

async def save_submission(
    db: AsyncSession,
    session_id: str,
    language: str,
    code: str,
    task_description: str,
    ai_feedback: str,
    mistake_tags: list[str],
    difficulty: int,
    score: float,
) -> Submission:
    sub = Submission(
        session_id=session_id,
        language=language,
        code=code,
        task_description=task_description,
        ai_feedback=ai_feedback,
        mistake_tags=",".join(mistake_tags),
        difficulty=difficulty,
        score=score,
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return sub


async def get_submission_history(db: AsyncSession, session_id: str, limit: int = 20) -> list[dict]:
    result = await db.execute(
        select(Submission)
        .where(Submission.session_id == session_id)
        .order_by(Submission.created_at.desc())
        .limit(limit)
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "language": r.language,
            "task_description": r.task_description,
            "score": r.score,
            "mistake_tags": r.mistake_tags.split(",") if r.mistake_tags else [],
            "difficulty": r.difficulty,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
