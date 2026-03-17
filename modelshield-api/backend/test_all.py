"""
ModelShield Full Test Suite
Run with: python test_all.py
"""
import os, sys

# Set DB URL BEFORE importing any project module
os.environ["DATABASE_URL"] = "sqlite:///./test_modelshield_suite.db"
if os.path.exists("test_modelshield_suite.db"):
    os.remove("test_modelshield_suite.db")

from fastapi.testclient import TestClient
import main

passed = 0
failed = 0

def check(label, condition, actual=None):
    global passed, failed
    if condition:
        print(f"  ✅ {label}")
        passed += 1
    else:
        print(f"  ❌ {label}" + (f" (got: {actual})" if actual is not None else ""))
        failed += 1

print("=" * 60)
print("MODELSHIELD COMPLETE TEST SUITE")
print("=" * 60)

# Use TestClient as context manager so lifespan runs (creates tables + seeds)
with TestClient(main.app) as client:

    # ─── [1] Core Endpoints ──────────────────────────────────────
    print("\n[1] Core Endpoints")
    r = client.get("/")
    check("GET / → 200 with name", r.status_code == 200 and r.json()["name"] == "ModelShield API")
    r = client.get("/health")
    check("GET /health → healthy", r.status_code == 200 and r.json()["status"] == "healthy")
    r = client.get("/models")
    check("GET /models → 8 models", len(r.json()) == 8, len(r.json()))
    r = client.get("/payments/packages")
    check("GET /payments/packages → 4 packages", len(r.json()) == 4)

    # ─── [2] Auth ────────────────────────────────────────────────
    print("\n[2] Auth")
    r = client.post("/auth/register", json={"email": "user@test.com", "password": "pass123"})
    check("Register → 200", r.status_code == 200 and "access_token" in r.json())
    ha = {"Authorization": f'Bearer {r.json()["access_token"]}'}

    r = client.post("/auth/login", json={"email": "user@test.com", "password": "pass123"})
    check("Login correct → 200", r.status_code == 200)
    r = client.post("/auth/register", json={"email": "user@test.com", "password": "pass123"})
    check("Duplicate email → 400", r.status_code == 400)
    r = client.post("/auth/login", json={"email": "user@test.com", "password": "wrong"})
    check("Wrong password → 401", r.status_code == 401)
    r = client.post("/auth/login", json={"email": "ghost@x.com", "password": "pass123"})
    check("Unknown user → 401", r.status_code == 401)
    r = client.get("/auth/me", headers=ha)
    check("/auth/me valid → 200", r.status_code == 200 and r.json()["email"] == "user@test.com")
    r = client.get("/auth/me", headers={"Authorization": "Bearer bad_token"})
    check("/auth/me bad JWT → 401", r.status_code == 401)
    r = client.post("/auth/register", json={"email": "x@x.com", "password": "12"})
    check("Short password → 400", r.status_code == 400)

    # ─── [3] API Keys ─────────────────────────────────────────────
    print("\n[3] API Keys")
    r = client.post("/keys/create", json={"name": "Main Key"}, headers=ha)
    check("Create key → 200", r.status_code == 200)
    key_id = r.json()["id"]; raw_key = r.json()["key"]
    check("Key has ms_ prefix", raw_key.startswith("ms_"))

    r = client.get("/keys", headers=ha)
    check("List keys → 1 key", len(r.json()) == 1)

    rb = client.post("/auth/register", json={"email": "other@test.com", "password": "pass123"})
    hb = {"Authorization": f'Bearer {rb.json()["access_token"]}'}
    bid = client.post("/keys/create", json={"name": "Other"}, headers=hb).json()["id"]
    check("Cannot delete other user's key → 404", client.delete(f"/keys/{bid}", headers=ha).status_code == 404)
    check("Delete own key → 200", client.delete(f"/keys/{key_id}", headers=ha).status_code == 200)
    check("Deleted key shows as revoked", client.get("/keys", headers=ha).json()[0]["status"] == "revoked")
    check("No auth → 401/403", client.post("/keys/create", json={"name": "x"}).status_code in (401, 403))

    # ─── [4] Usage ───────────────────────────────────────────────
    print("\n[4] Usage")
    r = client.get("/usage", headers=ha)
    check("GET /usage → 200 with logs", r.status_code == 200 and "logs" in r.json() and "total_tokens" in r.json())

    # ─── [5] Payment & UTR Security ──────────────────────────────
    print("\n[5] Payment & UTR Security")
    r = client.post("/payments/create", json={"package_id": 1}, headers=ha)
    check("Create payment → 200", r.status_code == 200 and "payment_id" in r.json())
    pid1 = r.json()["payment_id"]
    check("Amount has paise noise (unique)", r.json()["amount"] != 99.0)
    check("UPI link present", "upi_link" in r.json())

    r = client.post("/payments/submit-utr", json={"payment_id": pid1, "utr": "VALID001UTR"}, headers=ha)
    check("Submit UTR → 200", r.status_code == 200)

    r = client.post("/payments/submit-utr", json={"payment_id": pid1, "utr": "DIFF002UTR"}, headers=ha)
    check("Re-submit same payment → 400", r.status_code == 400)

    pid2 = client.post("/payments/create", json={"package_id": 2}, headers=ha).json()["payment_id"]
    r = client.post("/payments/submit-utr", json={"payment_id": pid2, "utr": "VALID001UTR"}, headers=ha)
    check("Reuse UTR on different payment → 400", r.status_code == 400)

    r = client.post("/payments/submit-utr", json={"payment_id": pid2, "utr": "AB"}, headers=ha)
    check("UTR too short → 400", r.status_code == 400)

    check("Invalid package → 400", client.post("/payments/create", json={"package_id": 99}, headers=ha).status_code == 400)
    r = client.get("/payments/status", headers=ha)
    check("GET /payments/status → 200", r.status_code == 200 and len(r.json()) > 0)

    # ─── [6] Admin ───────────────────────────────────────────────
    print("\n[6] Admin")
    ar = client.post("/auth/login", json={"email": "admin@modelshield.dev", "password": "admin123"})
    check("Admin login → 200", ar.status_code == 200, ar.json())
    ah = {"Authorization": f'Bearer {ar.json().get("access_token", "")}'}

    r = client.get("/admin/users", headers=ah)
    check("Admin: list users → 200 (≥2)", r.status_code == 200 and len(r.json()) >= 2)
    check("Non-admin blocked → 403", client.get("/admin/users", headers=ha).status_code == 403)
    check("Admin: list models → 8", len(client.get("/admin/models", headers=ah).json()) == 8)
    r = client.get("/admin/analytics", headers=ah)
    check("Admin: analytics has all fields", r.status_code == 200 and all(k in r.json() for k in ["total_users","total_tokens","total_revenue","total_requests"]))
    check("Admin: list provider keys → 200", client.get("/admin/provider-keys", headers=ah).status_code == 200)
    check("Admin: list payments → 200", client.get("/admin/payments", headers=ah).status_code == 200)

    # Verify payment
    cred_before = client.get("/auth/me", headers=ha).json()["credits"]
    r = client.post(f"/admin/payments/{pid1}/verify", headers=ah)
    check("Admin: verify payment → 200", r.status_code == 200)
    cred_after = client.get("/auth/me", headers=ha).json()["credits"]
    check("Credits added after verify", cred_after > cred_before, f"{cred_before}→{cred_after}")
    check("Double verify blocked → 400", client.post(f"/admin/payments/{pid1}/verify", headers=ah).status_code == 400)

    # Reject payment
    pid3 = client.post("/payments/create", json={"package_id": 1}, headers=ha).json()["payment_id"]
    client.post("/payments/submit-utr", json={"payment_id": pid3, "utr": "UTR_REJECT_ME"}, headers=ha)
    check("Admin: reject payment → 200", client.post(f"/admin/payments/{pid3}/reject", headers=ah).status_code == 200)

    # UTR on rejected
    pid4 = client.post("/payments/create", json={"package_id": 1}, headers=ha).json()["payment_id"]
    client.post(f"/admin/payments/{pid4}/reject", headers=ah)
    r = client.post("/payments/submit-utr", json={"payment_id": pid4, "utr": "TRY_REJECTED"}, headers=ha)
    check("UTR on rejected payment → 400", r.status_code == 400)

    # Add credits
    uid = client.get("/auth/me", headers=ha).json()["id"]
    check("Admin: add credits → 200", client.post(f"/admin/users/{uid}/add-credits", json={"amount": 100.0}, headers=ah).status_code == 200)
    check("Admin: negative credits → 400", client.post(f"/admin/users/{uid}/add-credits", json={"amount": -5}, headers=ah).status_code == 400)
    check("Admin: add credits nonexistent user → 404", client.post("/admin/users/99999/add-credits", json={"amount": 10}, headers=ah).status_code == 404)

    # Provider key CRUD
    check("Admin: add provider key → 200", client.post("/admin/provider-keys", json={"provider": "groq", "api_key": "gsk_test"}, headers=ah).status_code == 200)
    pk_id = client.get("/admin/provider-keys", headers=ah).json()[-1]["id"]
    check("Admin: delete provider key → 200", client.delete(f"/admin/provider-keys/{pk_id}", headers=ah).status_code == 200)
    check("Admin: delete nonexistent key → 404", client.delete("/admin/provider-keys/99999", headers=ah).status_code == 404)

    # Model management
    r = client.post("/admin/models", json={"name": "test-v1", "display_name": "Test", "provider": "groq", "endpoint": "https://x.com"}, headers=ah)
    check("Admin: create model → 200", r.status_code == 200)
    mid = r.json()["id"]
    check("Admin: toggle model status → 200", client.patch(f"/admin/models/{mid}", json={"status": "inactive"}, headers=ah).status_code == 200)
    check("Admin: patch nonexistent model → 404", client.patch("/admin/models/99999", json={"status": "active"}, headers=ah).status_code == 404)

    # ─── [7] AI Gateway ──────────────────────────────────────────
    print("\n[7] AI Gateway")
    gw_key = client.post("/keys/create", json={"name": "GW"}, headers=ha).json()["key"]
    gw_h = {"Authorization": f"Bearer {gw_key}"}
    r = client.post("/v1/chat/completions", json={"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": "hi"}]}, headers=gw_h)
    check("No provider key configured → 503", r.status_code == 503)
    r = client.post("/v1/chat/completions", json={"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": "hi"}]}, headers={"Authorization": "Bearer ms_fakefakefakefakefakefakefakefake1234567"})
    check("Invalid API key → 401", r.status_code == 401)
    r = client.post("/v1/chat/completions", json={"model": "nonexistent-xyz", "messages": [{"role": "user", "content": "hi"}]}, headers=gw_h)
    check("Unknown model → 404", r.status_code == 404)
    r = client.post("/v1/chat/completions", json={"model": "llama-3.1-8b-instant"}, headers=gw_h)
    check("No messages/no provider → 400 or 503", r.status_code in (400, 503))
    r = client.post("/v1/chat/completions", json={"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": "hi"}]})
    check("Missing auth header → 401", r.status_code == 401)

# ─── Results ─────────────────────────────────────────────────
print()
print("=" * 60)
total = passed + failed
print(f"RESULTS: {passed}/{total} passed, {failed} failed")
if failed == 0:
    print("🎉 ALL TESTS PASSED!")
else:
    print("⚠️  Some tests failed — see ❌ above")
print("=" * 60)

if os.path.exists("test_modelshield_suite.db"):
    os.remove("test_modelshield_suite.db")

sys.exit(0 if failed == 0 else 1)
