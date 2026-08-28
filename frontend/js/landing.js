const API = "";

// Subset + friendly labels for the homepage quick-report widget — the values
// sent are still the real backend category names from categories.js, just
// relabeled to match the compact 3x3 grid in the reference design.
const QUICK_CATS = [
  { key: "Pothole", label: "Road / Pothole" },
  { key: "Broken Streetlight", label: "Street Light" },
  { key: "Garbage Overflow", label: "Garbage" },
  { key: "Drainage Issue", label: "Drainage" },
  { key: "Water Leakage", label: "Water Leakage" },
  { key: "Traffic Signal", label: "Traffic Signal" },
  { key: "Public Toilet", label: "Public Toilet" },
  { key: "Damaged Footpath", label: "Footpath" },
  { key: "Other", label: "Other" },
];

// ---- Header auth menu + notifications dropdown ----
// (Notification bell + dropdown themselves are handled by notifications.js,
// shared across every page — it tracks read/unread state properly.)
CivicAuth.wireHeaderMenu();

// ---- Quick report category grid ----
const quickGrid = document.getElementById("quickCatGrid");
let quickSelected = "Pothole";

function renderQuickGrid() {
  quickGrid.innerHTML = "";
  QUICK_CATS.forEach(({ key, label }) => {
    const div = document.createElement("div");
    div.className = "l-cat" + (key === quickSelected ? " active" : "");
    div.innerHTML = `
      <div class="l-cat-check"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M20 6 9 17l-5-5"/></svg></div>
      ${CATEGORY_ICONS[key] || CATEGORY_ICONS["Other"]}
      <span>${label}</span>`;
    div.addEventListener("click", () => {
      quickSelected = key;
      renderQuickGrid();
    });
    quickGrid.appendChild(div);
  });
}
renderQuickGrid();

document.getElementById("quickNextBtn").addEventListener("click", () => {
  // The full step-by-step flow (photo, location, description, submit) lives
  // on citizen.html and is left intact — this hands off the chosen category
  // so citizen.html can pre-select it and skip straight to the remaining
  // fields, per the "auto-select category" behaviour.
  try { sessionStorage.setItem("jandrishti_quick_category", quickSelected); } catch (e) {}
  window.location.href = "/citizen.html";
});

// ---- Live stats + recent issues + map, all from the real API ----
const timeAgo = (iso) => {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
};

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

async function loadStats() {
  try {
    const res = await fetch(`${API}/api/stats`);
    const s = await res.json();
    const resolved = s.by_status?.RESOLVED || 0;
    const rate = s.total_incidents ? Math.round((resolved / s.total_incidents) * 100) : 0;

    document.getElementById("statReported").textContent = s.total_incidents.toLocaleString();
    document.getElementById("statResolved").textContent = resolved.toLocaleString();
    document.getElementById("statRate").textContent = `${rate}%`;

    document.getElementById("impactReported").textContent = s.total_incidents.toLocaleString();
    document.getElementById("impactResolved").textContent = resolved.toLocaleString();
  } catch (e) {
    ["statReported", "statResolved", "statRate"].forEach((id) => (document.getElementById(id).textContent = "—"));
  }
}

async function loadComplaints() {
  try {
    const res = await fetch(`${API}/api/complaints?sort=recent&only_primary=true`);
    const rows = await res.json();
    renderRecent(rows.slice(0, 4));
    renderMap(rows);

    const citizens = new Set(rows.map((r) => r.reporter_id).filter(Boolean));
    document.getElementById("impactCitizens").textContent = citizens.size
      ? citizens.size.toLocaleString()
      : rows.length.toLocaleString();
  } catch (e) {
    document.getElementById("recentList").innerHTML = `<div class="l-recent-empty">Couldn't load recent reports right now.</div>`;
    document.getElementById("impactCitizens").textContent = "—";
  }
}

function renderRecent(rows) {
  const list = document.getElementById("recentList");
  if (!rows.length) {
    list.innerHTML = `<div class="l-recent-empty">No reports yet — be the first to report an issue near you.</div>`;
    return;
  }
  list.innerHTML = rows.map((c) => {
    const level = (c.priority_level || "Low").toLowerCase();
    const thumb = c.image_path
      ? `<img class="l-recent-thumb" src="/uploads/${c.image_path.split("/").pop()}" alt="">`
      : `<div class="l-recent-thumb">${CATEGORY_ICONS[c.category] || CATEGORY_ICONS["Other"]}</div>`;
    const loc = c.address || `${c.latitude.toFixed(4)}, ${c.longitude.toFixed(4)}`;
    return `
      <div class="l-recent-item">
        ${thumb}
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
      </div>`;
  }).join("");
}

let leafletMap = null;
function renderMap(rows) {
  const el = document.getElementById("liveMap");
  if (!window.L || !el) return;
  if (!leafletMap) {
    leafletMap = L.map(el, { zoomControl: false, attributionControl: false }).setView([20.2961, 85.8245], 12);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>',
    }).addTo(leafletMap);

    // Same fix as dashboard.js: Leaflet measures its container's size at the
    // moment it's created, and in this flexbox card the final size isn't
    // settled yet on that first tick — so the map renders at the wrong size
    // until forced to re-measure.
    setTimeout(() => leafletMap.invalidateSize(), 150);
    window.addEventListener("resize", () => leafletMap.invalidateSize());
  }
  // Shared with dashboard.js so priority colors never drift between the two maps.
  const radiusFor = { Critical: 11, High: 9, Medium: 7, Low: 5 };
  const pts = [];
  rows.forEach((c) => {
    if (c.latitude == null || c.longitude == null) return;
    const color = PRIORITY_COLORS[c.priority_level] || "#8FA3B5";
    L.circleMarker([c.latitude, c.longitude], {
      radius: radiusFor[c.priority_level] || 6,
      color, fillColor: color, fillOpacity: 0.55, weight: 2,
    })
      .bindPopup(`<div style="min-width:160px"><div style="font-weight:600; margin-bottom:2px;">${c.category}</div><div style="display:flex; justify-content:space-between;"><span>Priority</span><b style="color:${color}">${c.priority_level} · ${c.priority_score}</b></div>${c.address ? `<div style="color:#8FA3B5; font-size:11.5px; margin-top:4px;">${c.address}</div>` : ""}</div>`)
      .addTo(leafletMap);
    pts.push([c.latitude, c.longitude]);
  });
  if (pts.length) leafletMap.fitBounds(pts, { padding: [24, 24], maxZoom: 13 });
}

loadStats();
loadComplaints();

// Previously these only loaded once at page load — if you filed a report and came
// back to the homepage, "Issues Reported" etc. wouldn't reflect it without a manual
// refresh. Poll periodically, and also refresh immediately when the tab regains
// focus (e.g. switching back from the citizen report form after submitting).
setInterval(() => { loadStats(); loadComplaints(); }, 20000);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") { loadStats(); loadComplaints(); }
});

// ---- Track complaint (in-page section, single-report lookup only) ----
function scoreBar(label, value) {
  const v = Math.max(0, Math.min(100, value || 0));
  return `
    <div class="l-score-row">
      <span class="l-score-label">${label}</span>
      <div class="l-score-track"><div class="l-score-fill" style="width:${v}%"></div></div>
      <span class="l-score-val">${v}</span>
    </div>`;
}

async function trackComplaint() {
  const id = document.getElementById("trackInput").value.trim();
  const out = document.getElementById("trackResult");
  if (!id) { out.innerHTML = `<div class="l-track-err">Enter a report ID first.</div>`; return; }
  out.innerHTML = `<div class="l-track-loading">Looking up ${id}&hellip;</div>`;
  try {
    const res = await fetch(`${API}/api/complaints/${encodeURIComponent(id)}`);
    if (!res.ok) throw new Error("not found");
    const c = await res.json();
    const statusSteps = ["RECEIVED", "ASSIGNED", "IN_PROGRESS", "RESOLVED"];
    const currentStep = Math.max(0, statusSteps.indexOf(c.status));

    out.innerHTML = `
      <div class="l-track-card">
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
          <div><span>Target response</span><b>${formatSla(c.sla_hours)}</b></div>
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
  } catch (e) {
    out.innerHTML = `<div class="l-track-err">No report found with ID "${id}". Double-check and try again.</div>`;
  }
}
document.getElementById("trackSubmit").addEventListener("click", trackComplaint);
document.getElementById("trackInput").addEventListener("keydown", (e) => { if (e.key === "Enter") trackComplaint(); });

// ---- FAQ accordion ----
document.querySelectorAll(".l-faq-item").forEach((item) => {
  item.querySelector(".l-faq-q").addEventListener("click", () => {
    const wasOpen = item.classList.contains("open");
    document.querySelectorAll(".l-faq-item.open").forEach((i) => i.classList.remove("open"));
    if (!wasOpen) item.classList.add("open");
  });
});

// ---- Contact form (UI-only in this prototype — no backend endpoint yet) ----
document.getElementById("contactForm")?.addEventListener("submit", (e) => {
  e.preventDefault();
  civicToast("Message sent — we'll get back to you soon.");
  e.target.reset();
});

// ---- Newsletter ----
document.getElementById("newsletterForm")?.addEventListener("submit", (e) => {
  e.preventDefault();
  civicToast("Subscribed! You'll get updates by email.");
  e.target.reset();
});

// ---- Every remaining static button gets real feedback instead of doing nothing ----
document.querySelectorAll("[data-toast]").forEach((el) => {
  el.addEventListener("click", (e) => {
    e.preventDefault();
    civicToast(el.dataset.toast);
  });
});
