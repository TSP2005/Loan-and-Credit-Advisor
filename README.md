# 🏦 Agentic AI Loan & Credit Advisor

An AI-powered, multi-agent loan advisory system that provides real-time personalized loan recommendations, credit analysis, and regulatory compliance guidance through a conversational chat interface.

---

## Prerequisites

- Python 3.11 or 3.13
- Node.js 18+ and npm
- A free [Groq API Key](https://console.groq.com)

---

## Setup & Running

### 1. Backend

```bash
# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1       # Windows PowerShell

# Install dependencies
pip install -r backend/requirements.txt
pip install duckduckgo-search

# Train the ML model (first time only)
cd backend
python ml_models/build_loan_risk_model.py
cd ..

# Start the backend server
uvicorn backend.main:app --port 8000
```

### 2. Frontend

```bash
cd frontend
npm install       # first time only
npm run dev
```

Open your browser at **http://localhost:5173**

---

## Environment Variables

Create a file at `backend/.env`:

```env
GROQ_API_KEY=your_groq_api_key_here
SECRET_KEY=any_long_random_secret_string
CHROMADB_PATH=./chromadb_storage
FAISS_PATH=./rag/faiss_index
LOG_LEVEL=DEBUG
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
MODEL_SAVE_PATH=./ml_models/saved
UPLOAD_DIR=./uploads
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI + Uvicorn |
| AI Orchestration | LangGraph |
| Agentic Framework | CrewAI |
| LLM Provider | Groq (LLaMa 3) |
| Risk ML Model | XGBoost |
| Policy Search | FAISS + sentence-transformers |
| User Database | ChromaDB |
| Real-time Chat | WebSocket |
| Frontend | React + Vite |

---

## Project Structure

```
loanv2/
├── backend/
│   ├── main.py              # FastAPI entry point
│   ├── agents/              # CrewAI AI agents
│   ├── orchestrator/        # LangGraph state machine
│   ├── ml_models/           # XGBoost, EMI calculator, rate predictor
│   ├── rag/                 # FAISS policy search pipeline
│   ├── routers/             # REST API + WebSocket endpoints
│   ├── auth/                # JWT authentication
│   └── tools/               # CrewAI tool wrappers
└── frontend/
    └── src/
        ├── pages/           # Dashboard, Login, Guest
        └── components/      # Chat, CreditGauge, EMI Calculator
```

---

For full technical documentation including architecture diagrams, end-to-end flow walkthroughs, and component explanations, see **`Project_Documentation.docx`**.
