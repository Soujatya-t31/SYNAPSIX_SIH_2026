const API = "";

if (!CivicAuth.isLoggedIn()) {
  window.location.href = "/account.html";
}

CivicAuth.wireHeaderMenu();

const STATUS_LABEL = {
  RECEIVED: "Submitted", ASSIGNED: "Assigned", IN_PROGRESS: "In Progress",
  RESOLVED: "Resolved", REOPENED: "Reopened",
};
const STATUS_COLOR = {
  RECEIVED: "#8FA3B5", ASSIGNED: "#E0912B", IN_PROGRESS: "#2E6E8E",
  RESOLVED: "#2E7D53", REOPENED: "#C1392B",
};
const SCORE_LABELS = [
  ["severity_score", "Severity"],
  ["public_impact_score", "Public Impact"],
  ["safety_risk_score", "Accident / Safety Risk"],
  ["location_criticality_score", "Location Criticality"],
  ["historical_recurrence_score", "Historical Recurrence"],
  ["future_risk_score", "Future Risk"],
];

const timeAgo = (iso) => {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
};

function scoreBar(label, value) {
  const v = Math.max(0, Math.min(100, value || 0));
  return `
    <div class="l-score-row">
      <span class="l-score-label">${label}</span>
      <div class="l-score-track"><div class="l-score-fill" style="width:${v}%"></div></div>
      <span class="l-score-val">${v}</span>
    </div>`;
}

function renderTrackCard(c) {
  const statusSteps = ["RECEIVED", "ASSIGNED", "IN_PROGRESS", "RESOLVED"];
  const currentStep = Math.max(0, statusSteps.indexOf(c.status));
  return `
    <div class="l-track-card" style="border:none; padding:16px 0 0;">
      <div class="l-track-head">
        <div>
          <div class="l-track-id mono">${c.id}</div>
          <div class="l-track-cat">${c.category}${c.address ? " · " + c.address : ""}</div>
        </div>
        <span class="badge ${(c.priority_level || "low").toLowerCase()}">${c.priority_level} · ${c.priority_score}/100</span>
      </div>

      <div class="l-track-steps">
        ${statusSteps.map((s, i) => `
          <div class="l-track-step ${i <= currentStep ? "done" : ""} ${c.status === s ? "current" : ""}">
            <span class="l-track-dot"></span>
            <span>${STATUS_LABEL[s]}</span>
          </div>`).join("")}
      </div>

      <div class="l-track-meta">
        <div><span>Department</span><b>${c.department}</b></div>
        <div><span>Reported</span><b>${timeAgo(c.created_at)}</b></div>
        <div><span>Target response</span><b>${c.sla_hours} hrs</b></div>
        <div><span>Image verified</span><b>${c.cv_valid ? "Yes" : "Needs review"}</b></div>
      </div>

      <div class="l-track-scores">
        <div class="l-score-row l-score-total">
          <span class="l-score-label">Total Priority Score</span>
          <div class="l-score-track"><div class="l-score-fill total" style="width:${c.priority_score}%"></div></div>
          <span class="l-score-val">${c.priority_score}</span>
        </div>
        ${SCORE_LABELS.map(([key, label]) => scoreBar(label, c[key])).join("")}
      </div>
    </div>`;
}

async function loadProfile() {
  const user = CivicAuth.getUser();
  document.getElementById("profileAvatar").textContent = (user.name || user.email).charAt(0).toUpperCase();
  document.getElementById("profileName").textContent = user.name;
  document.getElementById("profileEmail").textContent = user.email;

  const list = document.getElementById("myReportsList");
  try {
    const res = await fetch(`${API}/api/complaints?reporter_id=${encodeURIComponent(user.email)}&only_primary=false&sort=recent`, {
      headers: CivicAuth.authHeaders(),
    });
    const rows = await res.json();

    document.getElementById("pStatTotal").textContent = rows.length;
    document.getElementById("pStatResolved").textContent = rows.filter((r) => r.status === "RESOLVED").length;
    document.getElementById("pStatOpen").textContent = rows.filter((r) => r.status !== "RESOLVED").length;

    if (!rows.length) {
      list.innerHTML = `<div class="l-recent-empty">You haven't filed any reports yet. <a href="/citizen.html" class="l-link">Report your first issue &rarr;</a></div>`;
      return;
    }

    list.innerHTML = rows.map((c, i) => {
      const level = (c.priority_level || "Low").toLowerCase();
      const loc = c.address || `${c.latitude.toFixed(4)}, ${c.longitude.toFixed(4)}`;
      return `
        <div>
          <div class="l-recent-item p-report-row" data-idx="${i}">
            <div class="l-recent-thumb">${CATEGORY_ICONS[c.category] || CATEGORY_ICONS["Other"]}</div>
            <div class="l-recent-mid">
              <div class="l-recent-top">
                <span class="badge ${level}">${c.priority_level || "Low"}</span>
                <span class="l-recent-title">${c.category}</span>
              </div>
              <div class="l-recent-loc">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s7-7.58 7-12.5A7 7 0 0 0 5 9.5C5 14.42 12 22 12 22Z"/><circle cx="12" cy="9.5" r="2.5"/></svg>
                <span>${loc}</span>
              </div>
            </div>
            <div class="l-recent-right">
              <span class="l-recent-status" style="color:${STATUS_COLOR[c.status] || "#8FA3B5"}">${STATUS_LABEL[c.status] || c.status}</span>
              <span class="l-recent-time">${timeAgo(c.created_at)}</span>
            </div>
            <button class="p-track-btn" data-idx="${i}" type="button">Track &rarr;</button>
          </div>
          <div class="p-report-detail" id="detail-${i}"></div>
        </div>`;
    }).join("");

    // Track button expands a full status-pipeline card (same rich view as the
    // homepage's "Track Complaint" widget) inline, right here, per report — no
    // need to copy the complaint ID and go find the tracker separately.
    document.querySelectorAll(".p-track-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const idx = btn.dataset.idx;
        const detail = document.getElementById(`detail-${idx}`);
        const isOpen = detail.classList.contains("open");
        document.querySelectorAll(".p-report-detail.open").forEach((d) => d.classList.remove("open"));
        if (isOpen) return;
        detail.innerHTML = renderTrackCard(rows[idx]);
        detail.classList.add("open");
      });
    });
  } catch (e) {
    list.innerHTML = `<div class="l-recent-empty">Couldn't load your reports right now.</div>`;
  }
}

loadProfile();
