const API = "";

// If already logged in, no need to be here.
if (CivicAuth.isLoggedIn()) {
  window.location.href = "/index.html";
}

const params = new URLSearchParams(window.location.search);

function showTab(name) {
  document.querySelectorAll(".a-tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".a-form").forEach((f) => f.classList.toggle("a-hidden", f.dataset.panel !== name));
}
document.querySelectorAll(".a-tab").forEach((t) => t.addEventListener("click", () => showTab(t.dataset.tab)));
document.querySelectorAll("[data-switch]").forEach((a) => {
  a.addEventListener("click", (e) => { e.preventDefault(); showTab(a.dataset.switch); });
});

// Support clicking a reset link straight from an emailed message
// (account.html?resetToken=XXXX) — jump straight to the reset tab, prefilled.
const linkToken = params.get("resetToken");
if (linkToken) {
  showTab("reset");
  const resetTokenInput = document.getElementById("resetToken");
  if (resetTokenInput) resetTokenInput.value = linkToken;
}

function showError(id, message) {
  const el = document.getElementById(id);
  el.textContent = message;
  el.classList.add("show");
}
function hideError(id) {
  document.getElementById(id).classList.remove("show");
}

// ---- Password show/hide toggles ----
document.querySelectorAll(".a-pass-toggle").forEach((btn) => {
  btn.addEventListener("click", () => {
    const input = document.getElementById(btn.dataset.target);
    if (!input) return;
    const showing = input.type === "text";
    input.type = showing ? "password" : "text";
    btn.classList.toggle("showing", !showing);
    btn.setAttribute("aria-label", showing ? "Show password" : "Hide password");
  });
});

async function postForm(path, fields) {
  const fd = new FormData();
  Object.entries(fields).forEach(([k, v]) => fd.append(k, v));
  const res = await fetch(`${API}${path}`, { method: "POST", body: fd });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "Something went wrong.");
  return data;
}

// ---- Login ----
document.getElementById("loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  hideError("loginError");
  const btn = e.target.querySelector(".a-submit");
  btn.disabled = true; btn.textContent = "Signing in…";
  try {
    const data = await postForm("/api/auth/login", {
      email: document.getElementById("loginEmail").value,
      password: document.getElementById("loginPassword").value,
    });
    CivicAuth.setSession(data.token, data.user);
    window.location.href = "/index.html";
  } catch (err) {
    showError("loginError", err.message);
  } finally {
    btn.disabled = false; btn.textContent = "Sign In";
  }
});

// ---- Register ----
document.getElementById("registerForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  hideError("registerError");

  const password = document.getElementById("regPassword").value;
  const confirm = document.getElementById("regPasswordConfirm").value;
  if (password !== confirm) {
    showError("registerError", "Passwords don't match — please re-enter.");
    return;
  }

  const btn = e.target.querySelector(".a-submit");
  btn.disabled = true; btn.textContent = "Creating account…";
  try {
    const data = await postForm("/api/auth/register", {
      name: document.getElementById("regName").value,
      email: document.getElementById("regEmail").value,
      password: password,
    });
    CivicAuth.setSession(data.token, data.user);
    window.location.href = "/index.html";
  } catch (err) {
    showError("registerError", err.message);
  } finally {
    btn.disabled = false; btn.textContent = "Create Account";
  }
});

// ---- Forgot password ----
document.getElementById("forgotForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  hideError("forgotError");
  const note = document.getElementById("forgotNote");
  note.classList.add("a-hidden");
  const btn = e.target.querySelector(".a-submit");
  btn.disabled = true; btn.textContent = "Sending…";
  try {
    const data = await postForm("/api/auth/forgot-password", {
      email: document.getElementById("forgotEmail").value,
    });
    if (data.found === false) {
      // No account with that email — show as an error, not a false "success" note,
      // so it's obvious what happened instead of looking like a silent no-op.
      showError("forgotError", data.message);
    } else {
      note.classList.remove("a-hidden");
      if (data.emailed) {
        note.textContent = data.message;
      } else if (data.reset_token) {
        note.innerHTML = `${data.message}<br><br><b>Reset token:</b><br><span class="mono">${data.reset_token}</span>`;
        showTab("reset");
        document.getElementById("resetToken").value = data.reset_token;
      } else {
        note.textContent = data.message;
      }
    }
  } catch (err) {
    showError("forgotError", err.message);
  } finally {
    btn.disabled = false; btn.textContent = "Send Reset Token";
  }
});

// ---- Reset password ----
document.getElementById("resetForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  hideError("resetError");
  const btn = e.target.querySelector(".a-submit");
  btn.disabled = true; btn.textContent = "Updating…";
  try {
    await postForm("/api/auth/reset-password", {
      token: document.getElementById("resetToken").value,
      new_password: document.getElementById("resetPassword").value,
    });
    showTab("login");
    showError("loginError", "Password updated — please sign in with your new password.");
  } catch (err) {
    showError("resetError", err.message);
  } finally {
    btn.disabled = false; btn.textContent = "Update Password";
  }
});
