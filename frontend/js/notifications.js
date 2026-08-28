// Wires the notification bell (#notifBtn / #notifDropdown / #notifList) that
// already exists in the shared header markup. No-op if a page doesn't have
// that markup, or if nobody's logged in — matches the existing pattern in
// auth.js's wireHeaderMenu (silently skip missing elements).
const CivicNotifications = {
  POLL_MS: 15000,

  timeAgo(iso) {
    const diffMs = Date.now() - new Date(iso).getTime();
    const mins = Math.round(diffMs / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.round(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.round(hrs / 24)}d ago`;
  },

  async load() {
    const dot = document.querySelector("#notifBtn .l-notif-dot");
    const list = document.getElementById("notifList");
    if (!list || !CivicAuth.isLoggedIn()) return;

    try {
      const res = await fetch("/api/notifications", { headers: CivicAuth.authHeaders() });
      if (!res.ok) return;
      const data = await res.json();

      if (dot) dot.style.display = data.unread_count > 0 ? "block" : "none";

      if (!data.notifications.length) {
        list.innerHTML = `<div class="l-dropdown-item"><span>No updates yet — you'll see status changes on your reports here.</span></div>`;
        return;
      }
      list.innerHTML = data.notifications
        .map(
          (n) => `
        <div class="l-dropdown-item">
          <b>${n.title}</b>
          <span>${n.message}</span>
          <span style="opacity:0.7;">${this.timeAgo(n.created_at)}</span>
        </div>`
        )
        .join("");
    } catch (e) {
      // silent — notifications are a nice-to-have, never block the page
    }
  },

  async markRead() {
    if (!CivicAuth.isLoggedIn()) return;
    try {
      await fetch("/api/notifications/read", { method: "PATCH", headers: CivicAuth.authHeaders() });
      const dot = document.querySelector("#notifBtn .l-notif-dot");
      if (dot) dot.style.display = "none";
    } catch (e) {}
  },

  init() {
    const btn = document.getElementById("notifBtn");
    if (!btn) return;
    if (!CivicAuth.isLoggedIn()) {
      const dot = btn.querySelector(".l-notif-dot");
      if (dot) dot.style.display = "none";
      return;
    }
    this.load();
    setInterval(() => this.load(), this.POLL_MS);
    btn.addEventListener("click", () => {
      // Give the dropdown a moment to open, then mark as read.
      setTimeout(() => this.markRead(), 400);
    });
  },
};

CivicNotifications.init();
