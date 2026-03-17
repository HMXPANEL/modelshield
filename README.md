# ModelShield API 🛡️
**AI Model Gateway — One API key, access to Llama, Mixtral, GPT, Gemma and more.**

---

## 🐛 Bugs Fixed in This Version

| # | File | Bug | Fix |
|---|------|-----|-----|
| 1 | `database.py` | `seed_admin` checked `admin@gmail.com` but created `admin@gamil.com` (typo) — admin login always failed | Unified to `admin@modelshield.dev` |
| 2 | `database.py` | Render PostgreSQL `postgres://` URL not converted — SQLAlchemy 2.x requires `postgresql://` | Added URL rewrite in `_get_engine()` |
| 3 | `requirements.txt` | `bcrypt==4.0.1` broke `passlib` (removed `__about__` module) | Downgraded to `bcrypt==3.2.2` |
| 4 | `requirements.txt` | Missing `python-multipart` — FastAPI form handling crashed | Added `python-multipart==0.0.6` |
| 5 | `requirements.txt` | Missing `psycopg2-binary` — PostgreSQL on Render failed silently | Added `psycopg2-binary==2.9.9` |
| 6 | `requirements.txt` | `python-jose` missing `[cryptography]` extras | Fixed to `python-jose[cryptography]` |
| 7 | `main.py` | `uvicorn.run("main:app")` string import failed when run as `python backend/main.py` | Changed to `uvicorn.run(app, ...)` |
| 8 | `api.py` | `admin_toggle_model` used `data: dict` — FastAPI cannot auto-parse raw dict from JSON body | Replaced with `ModelUpdate` Pydantic model |
| 9 | `frontend/app.js` | `API_BASE` hardcoded to `http://localhost:8000` — broke on Render | Dynamic: uses `window.location.origin` on Render |
| 10 | `admin/admin.js` | `API_BASE` hardcoded to `http://localhost:8000` — broke on Render | Dynamic: uses `window.location.origin` on Render |
| 11 | `frontend/playground.html` | Used `sessionStorage` key with wrong key name — playground never worked | Fixed key storage + manual key entry fallback |
| 12 | `frontend/docs.html` | `curl`/Python examples hardcoded `localhost` URL | Now generated dynamically from `API_BASE` |
| 13 | `frontend/index.html` | `curl` example hardcoded `localhost` | Dynamic via JS |

---

## 📁 Project Structure

```
modelshield-api/
├── backend/
│   ├── main.py          # FastAPI app entrypoint
│   ├── database.py      # SQLAlchemy models + DB setup
│   ├── auth.py          # JWT authentication
│   ├── api.py           # All API endpoints
│   └── test_all.py      # Full test suite (56 checks)
├── frontend/            # User-facing web app
│   ├── index.html       # Landing page
│   ├── login.html
│   ├── signup.html
│   ├── dashboard.html
│   ├── api_keys.html
│   ├── models.html
│   ├── playground.html
│   ├── usage.html
│   ├── buy_credits.html
│   ├── docs.html
│   ├── styles.css
│   └── app.js
├── admin/               # Admin panel
│   ├── index.html       # Admin login
│   ├── analytics.html
│   ├── users.html
│   ├── models.html
│   ├── provider_keys.html
│   ├── payments.html
│   ├── admin.css
│   └── admin.js
├── database/
│   └── schema.sql       # Reference schema
├── .env.example
├── requirements.txt
├── render.yaml          # Render.com deployment config
├── termux_setup.sh      # One-click Termux setup
└── start.sh             # Quick start script
```

---

## 📱 Termux Setup (Android)

### One-time setup (run once)
```bash
bash termux_setup.sh
```

### Or manual step-by-step
```bash
# 1. Update Termux packages
pkg update && pkg upgrade -y

# 2. Install Python
pkg install python python-pip -y

# 3. Install dependencies (no Rust/Cargo needed)
pip install \
  fastapi==0.103.2 \
  uvicorn==0.24.0 \
  sqlalchemy==2.0.23 \
  "python-jose[cryptography]==3.3.0" \
  passlib==1.7.4 \
  bcrypt==3.2.2 \
  pydantic==1.10.14 \
  httpx==0.25.2 \
  python-dotenv==1.0.0 \
  python-multipart==0.0.6

# 4. Configure environment
cp .env.example .env
nano .env   # Add your API keys

# 5. Start the server
python backend/main.py
```

### Access on Termux
| URL | What it is |
|-----|-----------|
| http://localhost:8000 | API root |
| http://localhost:8000/app | Frontend |
| http://localhost:8000/admin-panel | Admin panel |
| http://localhost:8000/docs | Swagger UI |
| http://localhost:8000/health | Health check |

> **To access from phone browser:** use `http://localhost:8000/app`
> **To access from another device on same WiFi:** find your phone IP with `ifconfig` and use `http://<phone-ip>:8000/app`

---

## 🚀 Render.com Deployment

### Method A — render.yaml (recommended)
1. Push this project to GitHub
2. Go to [render.com](https://render.com) → New → Blueprint
3. Connect your GitHub repo
4. Render reads `render.yaml` automatically — it creates both the web service and PostgreSQL database
5. Add your secret env vars in the Render dashboard:
   - `GROQ_API_KEY`
   - `OPENAI_API_KEY`
   - `UPI_ID`
   - `ALLOWED_ORIGINS` → `https://your-app-name.onrender.com`

### Method B — Manual setup
| Setting | Value |
|---------|-------|
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn backend.main:app --host 0.0.0.0 --port $PORT` |
| **Environment** | Python 3 |

**Required env vars on Render:**
```
SECRET_KEY        = (generate: python -c "import secrets; print(secrets.token_hex(32))")
DATABASE_URL      = (copy Internal Database URL from Render PostgreSQL)
UPI_ID            = yourname@upi
ALLOWED_ORIGINS   = https://your-app.onrender.com
GROQ_API_KEY      = gsk_...    (optional, or add via Admin Panel)
```

---

## 🔑 Default Credentials

```
Admin email:    admin@modelshield.dev
Admin password: admin123
```

> **Change the admin password** after first login via the Admin Panel → Users → Add Credits won't expose it, but update it directly in the DB or add a change-password endpoint for production.

---

## ⚡ Quick API Usage

```bash
# 1. Register a user
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"yourpass"}'

# 2. Create an API key (use the token from step 1)
curl -X POST http://localhost:8000/keys/create \
  -H "Authorization: Bearer <your_jwt>" \
  -H "Content-Type: application/json" \
  -d '{"name":"My Key"}'

# 3. Call AI (use the ms_ key from step 2)
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer ms_your_key" \
  -H "Content-Type: application/json" \
  -d '{"model":"llama-3.1-8b-instant","messages":[{"role":"user","content":"Hello!"}]}'
```

---

## 🧪 Running Tests

```bash
cd backend
python test_all.py
# Expected: 56/56 passed ✅
```

---

## 🔐 Security Notes

- All provider API keys are stored server-side — **never exposed to users**
- User API keys are hashed with SHA-256 — raw keys shown only once at creation
- UTR numbers are unique-constrained at DB level — prevents payment fraud
- JWT tokens expire after 7 days
- CORS is configurable via `ALLOWED_ORIGINS` env var
- Set a strong `SECRET_KEY` in production (never use the default)

---

## 🤖 Supported AI Providers

| Provider | Models | Notes |
|----------|--------|-------|
| **Groq** | Llama 3.1 8B, 70B, Mixtral, Gemma 2 | Fastest inference, free tier available |
| **OpenAI** | GPT-4o Mini, GPT-3.5 Turbo | Paid models only |
| **NVIDIA NIM** | Llama 3.1 8B | Free tier available |
| **Together AI** | Mistral 7B | Free tier available |

Add provider keys via Admin Panel → Provider Keys, or set them in `.env`.
