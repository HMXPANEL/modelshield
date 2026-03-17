# 🛡️ ModelShield API

**AI API Gateway — Access multiple AI providers with a single API key**

ModelShield is a self-hosted AI gateway platform similar to OpenRouter. Access Llama, Mixtral, Gemma, GPT-4 and more through a single unified REST API.

---

## ✨ **Features**

- **AI Model Gateway** — Single endpoint for all AI providers
- **API Key Management** — Create & manage developer keys with rate limits
- **Credit Billing System** — Pay-per-token usage tracking
- **UPI Payment System** — Manual payment with admin verification
- **Developer Playground** — Test models in browser
- **Admin Dashboard** — Manage users, models, payments, analytics
- **Mobile Responsive** — Works on Android Termux + any mobile browser

---

## 🚀 **Termux Setup (Android)**

### **Step 1: Install dependencies**

```bash
pkg update && pkg upgrade -y
pkg install python python-pip sqlite git -y
```

### **Step 2: Clone / extract project**

```bash
cd ~
# If using git:
# git clone https://github.com/yourrepo/modelshield-api
cd modelshield-api
```

### **Step 3: Install Python packages**

```bash
pip install -r requirements.txt --break-system-packages
```

> **Note:** If bcrypt fails, try: `pip install bcrypt==4.0.1 --break-system-packages`

### **Step 4: Configure environment**

```bash
cp .env.example .env
nano .env
```

Edit `.env` with your API keys:
```
GROQ_API_KEY=gsk_your_key_here
UPI_ID=yourname@upi
SECRET_KEY=your-random-secret-key
```

### **Step 5: Start the server**

```bash
cd backend
python main.py
```

Or with uvicorn directly:
```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### **Step 6: Access the platform**

Open your phone browser and go to:

| URL | Description |
|-----|-------------|
| `http://localhost:8000` | API root |
| `http://localhost:8000/app` | Frontend (developer portal) |
| `http://localhost:8000/admin-panel` | Admin dashboard |
| `http://localhost:8000/docs` | Swagger API docs |

---

## 🔑 **Default Admin Credentials**

```
Email: admin@modelshield.dev
Password: admin123
```

**Change these immediately in production!**

---

## 📡 **API Usage**

### **Register & Login**

```bash
# Register
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"dev@example.com","password":"mypassword"}'

# Login
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"dev@example.com","password":"mypassword"}'
```

### **Create API Key**

```bash
curl -X POST http://localhost:8000/keys/create \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"My App Key"}'
```

### **Call AI Model**

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer ms_your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-3.1-8b-instant",
    "messages": [{"role":"user","content":"Explain quantum computing"}],
    "temperature": 0.7,
    "max_tokens": 1024
  }'
```

### **Python Integration**

```python
import requests

API_KEY = "ms_your_key_here"
BASE_URL = "http://localhost:8000"

def chat(prompt, model="llama-3.1-8b-instant"):
    response = requests.post(
        f"{BASE_URL}/v1/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}]
        }
    )
    return response.json()["choices"][0]["message"]["content"]

print(chat("Hello! Who are you?"))
```

---

## 🤖 **Supported Models**

| Model | Provider | Free | Context |
|-------|----------|------|---------|
| llama-3.1-8b-instant | Groq | ✅ | 131K |
| llama-3.1-70b-versatile | Groq | ❌ | 131K |
| mixtral-8x7b-32768 | Groq | ✅ | 32K |
| gemma2-9b-it | Groq | ✅ | 8K |
| gpt-4o-mini | OpenAI | ❌ | 128K |
| gpt-3.5-turbo | OpenAI | ❌ | 16K |
| meta/llama-3.1-8b-instruct | NVIDIA | ✅ | 131K |
| mistralai/mistral-7b-instruct-v0.3 | Together | ✅ | 32K |

---

## 💳 **UPI Payment Flow**

1. User selects credit package in `/app/buy_credits.html`
2. Backend generates unique payment amount (avoids collision)
3. Browser opens UPI deep link → User pays in UPI app
4. User submits UTR number
5. Admin verifies in `/admin-panel/payments.html`
6. Credits added to user account

---

## 🗂️ **Project Structure**

```
modelshield-api/
├── backend/
│   ├── main.py        # FastAPI app, CORS, routers, startup
│   ├── auth.py        # JWT auth, register, login
│   ├── api.py         # All endpoints + AI routing
│   └── database.py    # SQLAlchemy models + helpers
├── frontend/          # Developer portal (HTML/CSS/JS)
│   ├── index.html     # Landing page
│   ├── login.html
│   ├── signup.html
│   ├── dashboard.html
│   ├── api_keys.html
│   ├── models.html
│   ├── playground.html
│   ├── usage.html
│   ├── buy_credits.html
│   ├── docs.html
│   ├── app.js
│   └── styles.css
├── admin/             # Admin dashboard
│   ├── index.html     # Admin login
│   ├── analytics.html
│   ├── users.html
│   ├── models.html
│   ├── provider_keys.html
│   ├── payments.html
│   ├── admin.js
│   └── admin.css
├── database/
│   └── schema.sql
├── requirements.txt
├── .env.example
└── README.md
```

---

## 🔧 **Troubleshooting**

### **Port already in use**
```bash
# Find process
lsof -i :8000
# Kill it
kill -9 <PID>
```

### **bcrypt install fails on Termux**
```bash
pip install bcrypt==4.0.1 --break-system-packages
pip install passlib --break-system-packages
```

### **CORS errors in browser**
- Make sure backend is running on `localhost:8000`
- Check that `API_BASE` in `app.js` matches your server URL
- For remote access, update `allow_origins` in `main.py`

### **Database reset**
```bash
rm backend/modelshield.db
# Restart server — tables recreate automatically
```

---

## 🌐 **Access from other devices on same WiFi**

```bash
# Find your local IP
ip addr show | grep "inet " | grep -v 127.0.0.1

# Start server bound to all interfaces
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000

# Update API_BASE in frontend/app.js and admin/admin.js:
# const API_BASE = "http://YOUR_LOCAL_IP:8000"
```

---

## 📝 **License**

MIT — Free to use, modify and distribute.

---

**Built with ❤️ for developers. Runs anywhere Python runs — including Android Termux.**
