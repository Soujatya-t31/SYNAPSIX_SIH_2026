const API = "";

// Already signed in as an officer — go straight to the dashboard.
if (GovAuth.isLoggedIn()) {
  window.location.href = "/dashboard.html";
}

function showError(id, message) {
  const el = document.getElementById(id);
  el.textContent = message;
  el.classList.add("show");
}
function hideError(id) {
  document.getElementById(id).classList.remove("show");
}

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

document.getElementById("govLoginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  hideError("govLoginError");
  const btn = e.target.querySelector(".a-submit");
  btn.disabled = true; btn.textContent = "Signing in…";
  try {
    const fd = new FormData();
    fd.append("email", document.getElementById("govEmail").value);
    fd.append("password", document.getElementById("govPassword").value);
    const res = await fetch(`${API}/api/officer/auth/login`, { method: "POST", body: fd });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Sign-in failed.");
    GovAuth.setSession(data.token, data.officer);
    window.location.href = "/dashboard.html";
  } catch (err) {
    showError("govLoginError", err.message);
  } finally {
    btn.disabled = false; btn.textContent = "Sign In to Dashboard";
  }
});
