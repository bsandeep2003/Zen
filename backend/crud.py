"""
crud.py — Database operations for DebugSession, DebugAttempt, and Checkpoint.
"""
import json
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import User, DebugSession, DebugAttempt, Checkpoint


# ─── Debug Session CRUD ──────────────────────────────────────────────────────

async def create_debug_session(
    db: AsyncSession,
    session_id: str,
    project_path: str,
    initial_command: str,
    initial_error: str = "",
    max_attempts: int = 5,
) -> DebugSession:
    session = DebugSession(
        session_id=session_id,
        project_path=project_path,
        initial_command=initial_command,
        initial_error=initial_error,
        max_attempts=max_attempts,
        status="active",
        total_attempts=0,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def get_debug_session(db: AsyncSession, session_id: str) -> Optional[DebugSession]:
    result = await db.execute(
        select(DebugSession).where(DebugSession.session_id == session_id)
    )
    return result.scalar_one_or_none()


async def update_debug_session_status(
    db: AsyncSession, session_id: str, status: str
) -> Optional[DebugSession]:
    session = await get_debug_session(db, session_id)
    if session:
        session.status = status
        session.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(session)
    return session


async def increment_session_attempts(
    db: AsyncSession, session_id: str
) -> Optional[DebugSession]:
    session = await get_debug_session(db, session_id)
    if session:
        session.total_attempts += 1
        session.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(session)
    return session


# ─── Debug Attempt CRUD ──────────────────────────────────────────────────────

async def create_debug_attempt(
    db: AsyncSession,
    session_id: str,
    attempt_number: int,
    state: str = "observe",
    error_type: str = "",
    error_message: str = "",
    diagnosis: str = "",
    plan: str = "",
    patch_diff: str = "",
    files_modified: Optional[List[str]] = None,
    command_run: str = "",
    stdout: str = "",
    stderr: str = "",
    exit_code: int = -1,
    duration_ms: float = 0.0,
    llm_reasoning: str = "",
) -> DebugAttempt:
    attempt = DebugAttempt(
        session_id=session_id,
        attempt_number=attempt_number,
        state=state,
        error_type=error_type,
        error_message=error_message,
        diagnosis=diagnosis,
        plan=plan,
        patch_diff=patch_diff,
        files_modified=json.dumps(files_modified or []),
        command_run=command_run,
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        duration_ms=duration_ms,
        llm_reasoning=llm_reasoning,
    )
    db.add(attempt)
    await db.commit()
    await db.refresh(attempt)
    return attempt


async def get_session_attempts(
    db: AsyncSession, session_id: str
) -> List[DebugAttempt]:
    result = await db.execute(
        select(DebugAttempt)
        .where(DebugAttempt.session_id == session_id)
        .order_by(DebugAttempt.attempt_number.asc())
    )
    return list(result.scalars().all())


# ─── Checkpoint CRUD ─────────────────────────────────────────────────────────

async def create_checkpoint(
    db: AsyncSession,
    session_id: str,
    commit_hash: str,
    branch_name: str = "",
    description: str = "",
) -> Checkpoint:
    checkpoint = Checkpoint(
        session_id=session_id,
        commit_hash=commit_hash,
        branch_name=branch_name,
        description=description,
    )
    db.add(checkpoint)
    await db.commit()
    await db.refresh(checkpoint)
    return checkpoint


async def get_latest_checkpoint(
    db: AsyncSession, session_id: str
) -> Optional[Checkpoint]:
    result = await db.execute(
        select(Checkpoint)
        .where(Checkpoint.session_id == session_id)
        .order_by(Checkpoint.created_at.desc())
    )
    return result.scalars().first()


# ─── User CRUD ───────────────────────────────────────────────────────────────

async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.email == email.lower().strip()))
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    email: str,
    full_name: str,
    password_hash: str,
) -> User:
    user = User(
        email=email.lower().strip(),
        full_name=full_name.strip(),
        password_hash=password_hash,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

