// Shared, dependency-free auth/session helpers used by every page.
// The backend issues a signed bearer token (see backend/auth_utils.py) that we
// just store in localStorage and attach to requests — no cookies/CORS wrinkles.
const CivicAuth = {
  TOKEN_KEY: "jandrishti_token",
  USER_KEY: "jandrishti_user",

  getToken() {
    return localStorage.getItem(this.TOKEN_KEY);
  },
  getUser() {
    try { return JSON.parse(localStorage.getItem(this.USER_KEY) || "null"); }
    catch (e) { return null; }
  },
  isLoggedIn() {
    return !!this.getToken() && !!this.getUser();
  },
  setSession(token, user) {
    localStorage.setItem(this.TOKEN_KEY, token);
    localStorage.setItem(this.USER_KEY, JSON.stringify(user));
  },
  clearSession() {
    localStorage.removeItem(this.TOKEN_KEY);
    localStorage.removeItem(this.USER_KEY);
  },
  authHeaders() {
    const t = this.getToken();
    return t ? { Authorization: `Bearer ${t}` } : {};
  },

  // Wires up the shared header user-menu markup (present on index.html and
  // can be reused wherever the same IDs exist). Safe no-op if the elements
  // aren't on the page.
  wireHeaderMenu() {
    const avatar = document.getElementById("userAvatar");
    const label = document.getElementById("userLabel");
    const loginLink = document.getElementById("loginLink");
    const myReportsLink = document.getElementById("myReportsLink");
    const logoutLink = document.getElementById("logoutLink");
    if (!avatar || !label) return;

    const user = this.getUser();
    if (user) {
      avatar.textContent = (user.name || user.email || "?").trim().charAt(0).toUpperCase();
      label.textContent = `Hi, ${(user.name || user.email).split(" ")[0]}`;
      loginLink?.classList.add("l-hidden");
      myReportsLink?.classList.remove("l-hidden");
      logoutLink?.classList.remove("l-hidden");
    } else {
      avatar.textContent = "?";
      label.textContent = "Sign In";
      loginLink?.classList.remove("l-hidden");
      myReportsLink?.classList.add("l-hidden");
      logoutLink?.classList.add("l-hidden");
    }

    logoutLink?.addEventListener("click", (e) => {
      e.preventDefault();
      this.clearSession();
      window.location.reload();
    });

    // Dropdown open/close on click, per trigger.
    document.querySelectorAll(".l-dropdown-wrap").forEach((wrap) => {
      const trigger = wrap.querySelector("button");
      const menu = wrap.querySelector(".l-dropdown");
      if (!trigger || !menu) return;
      trigger.addEventListener("click", (e) => {
        e.stopPropagation();
        const isOpen = menu.classList.contains("open");
        document.querySelectorAll(".l-dropdown.open").forEach((m) => m.classList.remove("open"));
        if (!isOpen) menu.classList.add("open");
      });
    });
    document.addEventListener("click", () => {
      document.querySelectorAll(".l-dropdown.open").forEach((m) => m.classList.remove("open"));
    });
  },
};

function civicToast(message) {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove("show"), 2600);
}
