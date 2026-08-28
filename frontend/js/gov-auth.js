// Government-portal session helper — deliberately separate from CivicAuth
// (auth.js). Different storage keys, different token role, different login
// page (gov-login.html vs account.html). A citizen signing in on this browser
// and an officer signing in on this browser never share or overwrite each
// other's session.
const GovAuth = {
  TOKEN_KEY: "civicgov_token",
  OFFICER_KEY: "civicgov_officer",

  getToken() {
    return localStorage.getItem(this.TOKEN_KEY);
  },
  getOfficer() {
    try { return JSON.parse(localStorage.getItem(this.OFFICER_KEY) || "null"); }
    catch (e) { return null; }
  },
  isLoggedIn() {
    return !!this.getToken() && !!this.getOfficer();
  },
  setSession(token, officer) {
    localStorage.setItem(this.TOKEN_KEY, token);
    localStorage.setItem(this.OFFICER_KEY, JSON.stringify(officer));
  },
  clearSession() {
    localStorage.removeItem(this.TOKEN_KEY);
    localStorage.removeItem(this.OFFICER_KEY);
  },
  authHeaders() {
    const t = this.getToken();
    return t ? { Authorization: `Bearer ${t}` } : {};
  },

  // Call at the top of any government-only page. Redirects to the government
  // login page immediately if there's no valid officer session.
  requireLogin() {
    if (!this.isLoggedIn()) {
      window.location.href = "/gov-login.html";
    }
  },
};
