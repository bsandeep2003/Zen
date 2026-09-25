"""
main.py — FastAPI application entry point.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from database import init_db, get_db
from agent import analyse_code, generate_challenge
from crud import (
    get_or_create_profile,
    profile_to_dict,
    lean_profile_for_llm,
    update_profile_after_submission,
    record_mistakes,
    get_mistake_patterns,
    save_submission,
    get_submission_history,
)


# ─── Lifespan ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Zen — Self-Learning Code Editor API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Schemas ────────────────────────────────────────────────────────────────

class SubmitRequest(BaseModel):
    session_id: str
    language: str
    code: str
    task_description: str = ""


class ProfileRequest(BaseModel):
    session_id: str


class ChallengeRequest(BaseModel):
    session_id: str


# ─── Routes ─────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"status": "ok", "app": "Zen Code Editor API"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/session/new")
async def new_session():
    """Create a fresh anonymous session ID for the client."""
    return {"session_id": str(uuid.uuid4())}


@app.get("/profile/{session_id}")
async def get_profile(session_id: str, db: AsyncSession = Depends(get_db)):
    from agent import get_user_memories
    profile = await get_or_create_profile(db, session_id)
    data = await profile_to_dict(profile)
    mistakes = await get_mistake_patterns(db, session_id)
    data["mistake_patterns"] = mistakes
    data["memories"] = get_user_memories(session_id)
    return data


@app.post("/submit")
async def submit_code(req: SubmitRequest, db: AsyncSession = Depends(get_db)):
    """
    Core endpoint: analyse code, learn from mistakes, update profile with Mem0 memory.
    """
    if not req.code.strip():
        raise HTTPException(status_code=400, detail="Code cannot be empty.")

    # 1. Load learner profile
    profile = await get_or_create_profile(db, req.session_id)
    profile_dict = await profile_to_dict(profile)

    # 2. Ask the AI agent — pass only the lean profile to keep tokens low
    try:
        result = await analyse_code(
            code=req.code,
            language=req.language,
            task_description=req.task_description,
            profile=lean_profile_for_llm(profile_dict),
        )
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    score = float(result.get("score", 50))
    mistake_tags = [t.strip() for t in result.get("mistakes", []) if t.strip()]

    # 3. Persist mistakes + submission
    await record_mistakes(db, req.session_id, mistake_tags)
    sub = await save_submission(
        db,
        session_id=req.session_id,
        language=req.language,
        code=req.code,
        task_description=req.task_description,
        ai_feedback=result.get("feedback", ""),
        mistake_tags=mistake_tags,
        difficulty=profile.current_difficulty,
        score=score,
    )

    # 4. Update learner profile (rolling avg, adaptive difficulty)
    updated_profile = await update_profile_after_submission(
        db, profile, score, req.language
    )
    updated_dict = await profile_to_dict(updated_profile)
    from agent import get_user_memories
    updated_dict["memories"] = get_user_memories(req.session_id)

    return {
        "submission_id": sub.id,
        "score": score,
        "summary": result.get("summary", ""),
        "feedback": result.get("feedback", ""),
        "hint": result.get("hint", ""),
        "mistakes": mistake_tags,
        "test_cases": result.get("test_cases", []),
        "next_challenge": result.get("next_challenge", ""),
        "memory_insight": result.get("memory_insight", ""),
        "active_memories": result.get("active_memories", []),
        "profile": updated_dict,
    }


@app.post("/challenge")
async def get_challenge(req: ChallengeRequest, db: AsyncSession = Depends(get_db)):
    """Generate a new coding challenge adapted to the learner's profile."""
    profile = await get_or_create_profile(db, req.session_id)
    profile_dict = await profile_to_dict(profile)
    challenge = await generate_challenge(lean_profile_for_llm(profile_dict))
    return challenge


@app.get("/history/{session_id}")
async def get_history(session_id: str, limit: int = 20, db: AsyncSession = Depends(get_db)):
    history = await get_submission_history(db, session_id, limit=limit)
    return {"submissions": history}


@app.delete("/session/{session_id}")
async def reset_session(session_id: str, db: AsyncSession = Depends(get_db)):
    """Reset a learner's progress (for testing / fresh start)."""
    from sqlalchemy import delete
    from database import Submission, MistakePattern, LearnerProfile
    await db.execute(delete(Submission).where(Submission.session_id == session_id))
    await db.execute(delete(MistakePattern).where(MistakePattern.session_id == session_id))
    await db.execute(delete(LearnerProfile).where(LearnerProfile.session_id == session_id))
    await db.commit()
    return {"message": "Session reset successfully."}
