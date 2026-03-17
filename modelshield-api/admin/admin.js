const API_BASE = "http://localhost:8000";

function getToken() { return localStorage.getItem("ms_token"); }
function getUser() { try { return JSON.parse(localStorage.getItem("ms_user") || "null"); } catch { return null; } }
function setAuth(t, u) { localStorage.setItem("ms_token", t); localStorage.setItem("ms_user", JSON.stringify(u)); }
function clearAuth() { localStorage.removeItem("ms_token"); localStorage.removeItem("ms_user"); }

function requireAdmin() {
  const token = getToken();
  const user = getUser();
  if (!token || !user || !user.is_admin) {
    window.location.href = "index.html";
    return false;
  }
  return true;
}

async function apiFetch(path, options = {}) {
  const token = getToken();
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(API_BASE + path, { ...options, headers });
  if (res.status === 401 || res.status === 403) { clearAuth(); window.location.href = "index.html"; return null; }
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Request failed");
  return data;
}

function showAlert(msg, type = "info", id = "alert-container") {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = `<div class="alert alert-${type} fade-in"><strong>${msg}</strong></div>`;
  setTimeout(() => { if (el) el.innerHTML = ""; }, 5000);
}

function setLoading(btnId, loading) {
  const btn = document.getElementById(btnId);
  if (!btn) return;
  btn.disabled = loading;
  btn.dataset.orig = btn.dataset.orig || btn.innerHTML;
  btn.innerHTML = loading ? `<span class="spinner"></span>` : btn.dataset.orig;
}

function formatDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function formatNum(n) {
  if (!n) return "0";
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "K";
  return String(n);
}

function logout() { clearAuth(); window.location.href = "index.html"; }

function initSidebar() {
  const ham = document.getElementById("hamburger");
  const sb = document.getElementById("sidebar");
  const ov = document.getElementById("sidebar-overlay");
  if (!ham || !sb) return;
  ham.addEventListener("click", () => { sb.classList.toggle("open"); ov && ov.classList.toggle("open"); });
  ov && ov.addEventListener("click", () => { sb.classList.remove("open"); ov.classList.remove("open"); });
}

document.addEventListener("DOMContentLoaded", initSidebar);
