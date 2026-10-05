"""
main.py — FastAPI server and WebSocket backend for Zen Autonomous Agent.
"""
import asyncio
import json
import uuid
import os
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional

from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from database import init_db, get_db, SessionLocal, User
import crud
from auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
)
from zen_chat import (
    chat_with_zen,
    list_user_memories,
    build_memory_graph,
    save_user_memories,
)
from codebase.scanner import scan_project
from codebase.model import CodebaseModel
from terminal.executor import execute_command
from tools.filesystem import list_files, read_file, write_file, edit_file
from agent.session import (
    ActiveSession,
    get_active_session,
    register_active_session,
    unregister_active_session,
)
from agent.core import DebugAgentEngine


# ─── Lifespan ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Zen — Autonomous Debugging Agent API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Pydantic Request Schemas ───────────────────────────────────────────────

class StartSessionRequest(BaseModel):
    project_path: str = "."
    initial_command: str
    max_attempts: int = 5


class RunCommandRequest(BaseModel):
    project_path: str = "."
    command: str
    timeout: int = 30


class ReadFileRequest(BaseModel):
    project_path: str = "."
    file_path: str


class WriteFileRequest(BaseModel):
    project_path: str = "."
    file_path: str
    content: str


class RegisterRequest(BaseModel):
    full_name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


class SaveMemoryRequest(BaseModel):
    conversations: list[str] = []


def _user_public(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
    }


# ─── Auth Routes ─────────────────────────────────────────────────────────────

@app.post("/auth/register")
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    email = req.email.lower().strip()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email is required")
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    if not req.full_name.strip():
        raise HTTPException(status_code=400, detail="Full name is required")

    existing = await crud.get_user_by_email(db, email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = await crud.create_user(
        db,
        email=email,
        full_name=req.full_name,
        password_hash=hash_password(req.password),
    )
    token = create_access_token(user.id, user.email)
    return {"token": token, "user": _user_public(user)}


@app.post("/auth/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await crud.get_user_by_email(db, req.email)
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user.id, user.email)
    return {"token": token, "user": _user_public(user)}


@app.get("/auth/me")
async def auth_me(current_user: User = Depends(get_current_user)):
    return _user_public(current_user)


# ─── Zen Agent Chat & Memory ─────────────────────────────────────────────────

@app.post("/chat")
async def zen_chat(req: ChatRequest, current_user: User = Depends(get_current_user)):
    try:
        result = await chat_with_zen(str(current_user.id), req.message, req.history)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return result


@app.get("/chat/memories")
async def zen_memories(current_user: User = Depends(get_current_user)):
    memories = list_user_memories(str(current_user.id))
    return {"memories": memories, "total": len(memories)}


@app.post("/chat/memory")
async def zen_save_memory(
    req: SaveMemoryRequest,
    current_user: User = Depends(get_current_user),
):
    """Persist conversation text into the user's long-term memory."""
    try:
        result = save_user_memories(str(current_user.id), req.conversations)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return result


@app.get("/chat/graph")
async def zen_memory_graph(current_user: User = Depends(get_current_user)):
    return build_memory_graph(str(current_user.id))


# ─── Connection Manager for WebSockets ───────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, list[WebSocket]] = {}

    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)

    def disconnect(self, session_id: str, websocket: WebSocket):
        if session_id in self.active_connections:
            if websocket in self.active_connections[session_id]:
                self.active_connections[session_id].remove(websocket)

    async def broadcast(self, session_id: str, message: dict):
        if session_id in self.active_connections:
            for connection in self.active_connections[session_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass


manager = ConnectionManager()


# ─── REST Routes ─────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "status": "ok",
        "app": "Zen Autonomous Debugging Agent API",
        "version": "2.0",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/agent/start")
async def start_agent_session(req: StartSessionRequest, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """Start an autonomous debugging session on a project path and error command."""
    proj_path = str(Path(req.project_path).resolve())
    session_id = f"session-{str(uuid.uuid4())[:8]}"

    # Save session to DB
    session_record = await crud.create_debug_session(
        db,
        session_id=session_id,
        project_path=proj_path,
        initial_command=req.initial_command,
        max_attempts=req.max_attempts,
    )

    # Instantiate ActiveSession in memory
    active_sess = ActiveSession(
        session_id=session_id,
        project_path=proj_path,
        initial_command=req.initial_command,
        max_attempts=req.max_attempts,
    )

    # Hook up WebSocket broadcasting
    async def session_broadcaster(payload: dict):
        await manager.broadcast(session_id, payload)

    active_sess.add_subscriber(session_broadcaster)
    register_active_session(active_sess)

    # Start immediately so the loop is not tied to the HTTP request lifecycle.
    engine = DebugAgentEngine(active_sess)
    asyncio.create_task(engine.run_debugging_loop())

    return {
        "session_id": session_id,
        "status": "started",
        "project_path": proj_path,
        "initial_command": req.initial_command,
    }


@app.get("/agent/session/{session_id}")
async def get_session_info(session_id: str, db: AsyncSession = Depends(get_db)):
    """Get status and history of attempts for a session."""
    session_record = await crud.get_debug_session(db, session_id)
    if not session_record:
        raise HTTPException(status_code=404, detail="Session not found")

    active = get_active_session(session_id)
    attempts = await crud.get_session_attempts(db, session_id)

    attempt_payload = [
        {
            "attempt_number": a.attempt_number,
            "state": a.state,
            "diagnosis": a.diagnosis,
            "patch_diff": a.patch_diff,
            "command_run": a.command_run,
            "stdout": a.stdout,
            "stderr": a.stderr,
            "exit_code": a.exit_code,
        }
        for a in attempts
    ]
    if active and active.attempts:
        attempt_payload = active.attempts

    return {
        "session_id": session_record.session_id,
        "project_path": (active.project_path if active else session_record.project_path),
        "initial_command": (active.initial_command if active else session_record.initial_command),
        "status": active.status if active else session_record.status,
        "state": active.state if active else session_record.status,
        "total_attempts": active.current_attempt_number if active else session_record.total_attempts,
        "attempts": attempt_payload,
    }


@app.post("/agent/run")
async def run_command_endpoint(req: RunCommandRequest):
    """Manually execute a command in project directory."""
    proj_path = str(Path(req.project_path).resolve())
    result = await execute_command(req.command, cwd=proj_path, timeout=req.timeout)
    return result.to_dict()


@app.get("/agent/codebase")
async def get_codebase_endpoint(project_path: str = "."):
    """Get full scan of project codebase (file tree, stack, git, symbols)."""
    proj_path = str(Path(project_path).resolve())
    model = CodebaseModel(project_root=proj_path)
    scan_project(proj_path, model)
    return model.to_dict()


@app.post("/agent/file/read")
async def read_file_endpoint(req: ReadFileRequest):
    """Read file content."""
    proj_path = str(Path(req.project_path).resolve())
    try:
        content = read_file(proj_path, req.file_path)
        return {"file_path": req.file_path, "content": content}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/agent/file/write")
async def write_file_endpoint(req: WriteFileRequest):
    """Write or update file content."""
    proj_path = str(Path(req.project_path).resolve())
    try:
        msg = write_file(proj_path, req.file_path, req.content)
        return {"status": "ok", "message": msg}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/agent/stop/{session_id}")
async def stop_agent_session(session_id: str, db: AsyncSession = Depends(get_db)):
    """Stop active debug session."""
    active_sess = get_active_session(session_id)
    if active_sess:
        active_sess.status = "stopped"
        unregister_active_session(session_id)
    await crud.update_debug_session_status(db, session_id, "stopped")
    return {"session_id": session_id, "status": "stopped"}


# ─── Memory Endpoints ────────────────────────────────────────────────────────

from memory.store import get_memory_summary, load_fixes, has_memory


@app.get("/agent/memory")
async def get_project_memory(project_path: str = "."):
    """Get the .zen/ memory summary for a project."""
    proj_path = str(Path(project_path).resolve())
    summary = get_memory_summary(proj_path)
    return summary


@app.get("/agent/memory/fixes")
async def get_project_fixes(project_path: str = "."):
    """Get all recorded fixes for a project."""
    proj_path = str(Path(project_path).resolve())
    fixes = load_fixes(proj_path)
    return {"fixes": fixes, "total": len(fixes)}


@app.get("/agent/memory/status")
async def get_memory_status(project_path: str = "."):
    """Check if a project has .zen/ memory."""
    proj_path = str(Path(project_path).resolve())
    return {"has_memory": has_memory(proj_path), "project_path": proj_path}



# ─── WebSocket Endpoint ──────────────────────────────────────────────────────

@app.websocket("/ws/agent/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await manager.connect(session_id, websocket)
    active_sess = get_active_session(session_id)
    if active_sess:
        await websocket.send_json({
            "event": "snapshot",
            "session_id": session_id,
            "state": active_sess.state,
            "status": active_sess.status,
            "project_path": active_sess.project_path,
            "initial_command": active_sess.initial_command,
            "current_attempt": active_sess.current_attempt_number,
        })
        for event in active_sess.event_log:
            try:
                await websocket.send_json(event)
            except Exception:
                break
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(session_id, websocket)
