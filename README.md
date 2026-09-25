# Zen — Self-Learning AI Code Editor

A fully adaptive online code editor powered by **Groq AI** + **FastAPI** + **React** + **SQLite**.

The AI agent watches every submission, tracks recurring mistake patterns, and progressively adapts its explanations, hints, test cases, and challenge difficulty to each individual developer.

---

## Project Structure

```
Zen/
├── backend/
│   ├── main.py          # FastAPI app + all routes
│   ├── agent.py         # Groq AI agent (self-learning logic)
│   ├── crud.py          # SQLAlchemy async CRUD helpers
│   ├── database.py      # DB schema: Submission, MistakePattern, LearnerProfile
│   ├── requirements.txt
│   └── .env             # Add your GROQ_API_KEY here
└── frontend/
    ├── src/
    │   ├── App.js        # Main IDE layout
    │   ├── api.js        # Axios client
    │   ├── hooks/useSession.js
    │   └── components/
    │       ├── AIPanel.js
    │       ├── ProfilePanel.js
    │       └── HistoryPanel.js
    └── .env
```

---

## Setup

### 1. Backend

```bash
cd backend

# Create & activate virtual environment
python -m venv .venv
.venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Add your Groq API key
copy .env.example .env
# Edit .env and set GROQ_API_KEY=gsk_...

# Start the server
uvicorn main:app --reload --port 8000
```

### 2. Frontend

```bash
cd frontend
npm start
```

Open http://localhost:3000

---

## How the Self-Learning Works

The AI builds a personalised system prompt for each learner:
- Top recurring mistake tags are injected into the prompt
- The agent weaves targeted micro-lessons around those patterns
- Difficulty automatically increases when avg score >= 80, decreases when <= 40
- Challenges are generated to specifically target the learner's weak areas

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /session/new | Create anonymous session |
| GET | /profile/{session_id} | Full learner profile + mistake patterns |
| POST | /submit | Submit code -> get AI feedback |
| POST | /challenge | Generate adaptive challenge |
| GET | /history/{session_id} | Submission history |
| DELETE | /session/{session_id} | Reset learning progress |

---

## Environment Variables

backend/.env
```
GROQ_API_KEY=gsk_your_key_here
DATABASE_URL=sqlite+aiosqlite:///./zen.db
MODEL_ID=llama-3.3-70b-versatile
```

frontend/.env
```
REACT_APP_API_URL=http://localhost:8000
```
