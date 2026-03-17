const API_BASE = "http://localhost:8000";

// ── Auth helpers ──────────────────────────────────────────────────────────────
function getToken() { return localStorage.getItem("ms_token"); }
function getUser() { try { return JSON.parse(localStorage.getItem("ms_user") || "null"); } catch { return null; } }
function setAuth(token, user) { localStorage.setItem("ms_token", token); localStorage.setItem("ms_user", JSON.stringify(user)); }
function clearAuth() { localStorage.removeItem("ms_token"); localStorage.removeItem("ms_user"); }
function isLoggedIn() { return !!getToken(); }

function requireAuth() {
  if (!isLoggedIn()) { window.location.href = "/app/login.html"; return false; }
  return true;
}

function requireAdmin() {
  const user = getUser();
  if (!user || !user.is_admin) { window.location.href = "/app/login.html"; return false; }
  return true;
}

// ── API fetch wrapper ─────────────────────────────────────────────────────────
async function apiFetch(path, options = {}) {
  const token = getToken();
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  try {
    const res = await fetch(API_BASE + path, { ...options, headers });
    if (res.status === 401) { clearAuth(); window.location.href = "/app/login.html"; return null; }
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Request failed");
    return data;
  } catch (e) { throw e; }
}

// ── UI helpers ────────────────────────────────────────────────────────────────
function showAlert(msg, type = "info", containerId = "alert-container") {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = `<div class="alert alert-${type} fade-in"><strong>${msg}</strong></div>`;
  setTimeout(() => { el.innerHTML = ""; }, 5000);
}

function setLoading(btnId, loading) {
  const btn = document.getElementById(btnId);
  if (!btn) return;
  btn.disabled = loading;
  btn.dataset.original = btn.dataset.original || btn.innerHTML;
  btn.innerHTML = loading
    ? `<span class="spinner" style="width:16px;height:16px;border-width:2px;"></span>`
    : btn.dataset.original;
}

function formatDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function formatNumber(n) {
  if (n === null || n === undefined) return "0";
  if (n >= 1000000) return (n / 1000000).toFixed(1) + "M";
  if (n >= 1000) return (n / 1000).toFixed(1) + "K";
  return String(n);
}

async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch { return false; }
}

// ── Sidebar mobile toggle ─────────────────────────────────────────────────────
function initSidebar() {
  const ham = document.getElementById("hamburger");
  const sidebar = document.getElementById("sidebar");
  const overlay = document.getElementById("sidebar-overlay");
  if (!ham || !sidebar) return;
  ham.addEventListener("click", () => {
    sidebar.classList.toggle("open");
    overlay && overlay.classList.toggle("open");
  });
  overlay && overlay.addEventListener("click", () => {
    sidebar.classList.remove("open");
    overlay.classList.remove("open");
  });
}

// ── Navbar user info ──────────────────────────────────────────────────────────
function initNavbar() {
  const user = getUser();
  if (!user) return;
  const emailEl = document.getElementById("nav-email");
  const creditsEl = document.getElementById("nav-credits");
  if (emailEl) emailEl.textContent = user.email;
  if (creditsEl) creditsEl.textContent = `⚡ ${parseFloat(user.credits || 0).toFixed(1)} credits`;
}

function logout() {
  clearAuth();
  window.location.href = "/app/login.html";
}

document.addEventListener("DOMContentLoaded", () => {
  initSidebar();
  initNavbar();
});
