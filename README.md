# PlacementCoach — Backend

FastAPI backend for the PlacementCoach AI placement guidance platform.

## Stack
- **FastAPI** — async Python web framework
- **Neon** — serverless PostgreSQL
- **Amazon S3** — PDF resume storage
- **OpenAI GPT-4o-mini** — AI analysis
- **asyncpg** — async Postgres driver
- **python-jose** — JWT auth
- **pdfplumber** — PDF text extraction

---

## Local Setup

### 1. Clone & install
```bash
git clone https://github.com/yourname/placementcoach-backend
cd placementcoach-backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
# Fill in your Neon DATABASE_URL, AWS keys, OpenAI key, SECRET_KEY
```

### 3. Run database migrations
```bash
psql $DATABASE_URL -f app/db/migrations/001_init.sql
```

### 4. Start the server
```bash
uvicorn app.main:app --reload --port 8000
```

API docs available at: http://localhost:8000/docs

---

## API Routes

| Method | Route | Auth | Description |
|--------|-------|------|-------------|
| POST | `/auth/register` | No | Register new user |
| POST | `/auth/login` | No | Login, get JWT |
| POST | `/resume/upload` | JWT | Upload PDF resume |
| GET | `/resume/{id}/download-url` | JWT | Get S3 presigned URL |
| POST | `/analysis/analyze-profile` | JWT | Full AI analysis |
| POST | `/analysis/generate-plan` | JWT | Generate action plan |
| GET | `/analysis/history` | JWT | Last 5 analyses |
| GET | `/me/results` | JWT | Dashboard data |
| GET | `/me/profile` | JWT | Student profile |
| GET | `/health` | No | Health check |

---

## S3 Bucket Setup

1. Create a private S3 bucket (e.g., `placementcoach-resumes`)
2. Block all public access
3. Create an IAM user with `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject` on your bucket
4. Use those credentials in `.env`

---

## Run Tests
```bash
pytest tests/ -v
```

---

## Deploy to Render

1. Push to GitHub
2. New Web Service on Render → connect repo
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
5. Add all `.env` variables in Render dashboard → Environment
