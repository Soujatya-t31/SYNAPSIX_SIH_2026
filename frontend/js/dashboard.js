const API = "";

let allComplaints = [];
let markers = {};
let map;
let activeLevelFilter = "";
let activeStatusFilter = "";
let currentView = "queue";

const FACTOR_META = [
  { key: "severity_score", label: "Severity", weight: 0.30 },
  { key: "public_impact_score", label: "Public Impact", weight: 0.20 },
  { key: "safety_risk_score", label: "Safety Risk", weight: 0.15 },
  { key: "location_criticality_score", label: "Location Criticality", weight: 0.15 },
  { key: "historical_recurrence_score", label: "Historical Recurrence", weight: 0.10 },
  { key: "future_risk_score", label: "Future Risk", weight: 0.10 },
];

// ---- Officer session / topbar ----
function initOfficerBadge() {
  const officer = GovAuth.getOfficer();
  if (!officer) return;
  document.getElementById("officerName").textContent = officer.name;
  document.getElementById("officerDept").textContent = officer.department;
}
document.getElementById("govLogoutBtn").addEventListener("click", () => {
  GovAuth.clearSession();
  window.location.href = "/gov-login.html";
});

// ---- View toggle (Priority Queue <-> Departments <-> Categories) ----
document.querySelectorAll("#viewToggle button").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("#viewToggle button").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    currentView = btn.dataset.view;
    document.getElementById("queueView").classList.toggle("c-hidden", currentView !== "queue");
    document.getElementById("departmentsView").classList.toggle("c-hidden", currentView !== "departments");
    document.getElementById("categoriesView").classList.toggle("c-hidden", currentView !== "categories");
    if (currentView === "departments") loadDepartments();
    else if (currentView === "categories") loadCategories();
    else setTimeout(() => map && map.invalidateSize(), 50);
  });
});

function showToast(message) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove("show"), 3200);
}

// ---- Map setup ----
const TILE_URL = {
  dark: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
  light: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
};
let tileLayer;

function currentTheme() {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

function initMap() {
  map = L.map("map", { zoomControl: true, attributionControl: true }).setView([20.2961, 85.8245], 12);
  tileLayer = L.tileLayer(TILE_URL[currentTheme()], {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>',
    maxZoom: 19,
  }).addTo(map);

  // BUG FIX: Leaflet measures its container's size at the moment it's created.
  // In a flexbox layout, the #map div's final width/height often isn't settled
  // yet on that first tick, so Leaflet renders at the wrong size — tiles then
  // appear to spill over / overlap the sidebar and stat strip instead of staying
  // inside the map panel. Forcing a re-measure after layout settles, and again
  // on every window resize, keeps the map correctly boxed in.
  setTimeout(() => map.invalidateSize(), 150);
  window.addEventListener("resize", () => map.invalidateSize());

  // Swap the basemap when the theme toggle is used, so the map matches the
  // rest of the command center instead of staying dark in light mode.
  document.addEventListener("civic-theme-change", (e) => {
    if (!map || !tileLayer) return;
    map.removeLayer(tileLayer);
    tileLayer = L.tileLayer(TILE_URL[e.detail.theme === "dark" ? "dark" : "light"], {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>',
      maxZoom: 19,
    }).addTo(map);
  });
}

function markerFor(c) {
  const color = PRIORITY_COLORS[c.priority_level] || "#8FA3B5";
  const radius = { Critical: 11, High: 9, Medium: 7, Low: 5 }[c.priority_level] || 6;
  return L.circleMarker([c.latitude, c.longitude], {
    radius,
    color: color,
    weight: 2,
    fillColor: color,
    fillOpacity: 0.55,
  }).bindPopup(popupHtml(c));
}

function popupHtml(c) {
  return `<div style="min-width:180px">
    <div style="font-weight:600; margin-bottom:2px;">${c.category}</div>
    <div style="color:#8FA3B5; font-size:11.5px; margin-bottom:6px;">${c.id}</div>
    <div style="display:flex; justify-content:space-between;">
      <span>Priority</span><b style="color:${PRIORITY_COLORS[c.priority_level]}">${c.priority_level} · ${c.priority_score}</b>
    </div>
    <div style="display:flex; justify-content:space-between;"><span>Affected</span><b>${c.affected_citizens}</b></div>
  </div>`;
}

function renderMarkers(list) {
  Object.values(markers).forEach((m) => map.removeLayer(m));
  markers = {};
  list.forEach((c) => {
    const m = markerFor(c);
    m.on("click", () => openDetail(c.id));
    m.addTo(map);
    markers[c.id] = m;
  });
}

// ---- Stats ----
async function loadStats() {
  const res = await fetch(`${API}/api/stats`);
  const s = await res.json();
  document.getElementById("statTotal").textContent = s.total_incidents;
  document.getElementById("statCritical").textContent = s.by_level.Critical;
  document.getElementById("statHigh").textContent = s.by_level.High;
  document.getElementById("statMedium").textContent = s.by_level.Medium;
  document.getElementById("statLow").textContent = s.by_level.Low;
  document.getElementById("statAffected").textContent = s.total_affected_citizens;
}

// ---- Departments view ----
const STATUS_LABEL_SHORT = {
  RECEIVED: "Received", ASSIGNED: "Assigned", IN_PROGRESS: "In progress", RESOLVED: "Resolved", REOPENED: "Reopened",
};

async function loadDepartments() {
  const grid = document.getElementById("deptGrid");
  try {
    const res = await fetch(`${API}/api/departments`, { headers: GovAuth.authHeaders() });
    if (res.status === 401) { GovAuth.clearSession(); window.location.href = "/gov-login.html"; return; }
    const depts = await res.json();
    if (!depts.length) {
      grid.innerHTML = `<div class="d-empty">No departments found.</div>`;
      return;
    }
    grid.innerHTML = depts.map(deptCardHtml).join("");
    grid.querySelectorAll("[data-open-id]").forEach((row) => {
      row.addEventListener("click", () => openDetail(row.dataset.openId));
    });
  } catch (e) {
    grid.innerHTML = `<div class="d-empty">Couldn't load departments right now.</div>`;
  }
}

function deptCardHtml(d) {
  const open = d.by_status.RECEIVED || 0;
  const assigned = d.by_status.ASSIGNED || 0;
  const inProgress = d.by_status.IN_PROGRESS || 0;
  const resolved = d.by_status.RESOLVED || 0;
  const officerNames = (d.officers || []).map((o) => o.name).join(", ") || "Unstaffed";
  const tasks = (d.active_tasks || [])
    .map((t) => `
      <div class="d-dept-task" data-open-id="${t.id}">
        <span class="stripe" style="background:${PRIORITY_COLORS[t.priority_level] || "#8FA3B5"}"></span>
        <div class="body">
          <div class="top"><span class="cat">${t.category}</span><span class="score" style="color:${PRIORITY_COLORS[t.priority_level] || "#8FA3B5"}">${t.priority_score}</span></div>
          <div class="meta">${t.id} · ${STATUS_LABEL_SHORT[t.status] || t.status} · reported by ${t.reporter_name || t.reporter_id || "Anonymous"}</div>
        </div>
      </div>`)
    .join("") || `<div class="d-dept-empty">No active tasks in this department right now.</div>`;

  return `
    <div class="d-dept-card">
      <div class="d-dept-head">
        <div class="d-dept-name">${d.department}</div>
        <div class="d-dept-staff">${officerNames}</div>
      </div>
      <div class="d-dept-counts">
        <div><b>${open}</b><span>Received</span></div>
        <div><b>${assigned}</b><span>Assigned</span></div>
        <div><b>${inProgress}</b><span>In progress</span></div>
        <div><b class="resolved">${resolved}</b><span>Resolved</span></div>
      </div>
      <div class="d-dept-section-label">Active tasks (${d.active_tasks.length})</div>
      <div class="d-dept-tasks">${tasks}</div>
    </div>`;
}

// ---- Categories view (universal counter — every category, reported vs resolved) ----
async function loadCategories() {
  const grid = document.getElementById("catGrid");
  try {
    const res = await fetch(`${API}/api/stats`);
    if (!res.ok) throw new Error("stats fetch failed");
    const s = await res.json();
    const categories = s.all_categories || Object.keys(s.by_category || {});

    let totalReported = 0;
    let totalResolved = 0;

    const cards = categories
      .map((cat) => {
        const reported = (s.by_category || {})[cat] || 0;
        const resolved = (s.by_category_resolved || {})[cat] || 0;
        const open = Math.max(0, reported - resolved);
        totalReported += reported;
        totalResolved += resolved;
        const pct = reported > 0 ? Math.round((resolved / reported) * 100) : 0;
        return `
          <div class="d-cat-card">
            <div class="d-cat-name">${cat}</div>
            <div class="d-cat-row"><span class="l">Reported</span><span class="v">${reported}</span></div>
            <div class="d-cat-row"><span class="l">Resolved</span><span class="v resolved">${resolved}</span></div>
            <div class="d-cat-row"><span class="l">Open</span><span class="v">${open}</span></div>
            <div class="d-cat-bar-track"><div class="d-cat-bar-fill" style="width:${pct}%"></div></div>
            <div class="d-cat-rate">${pct}% resolved</div>
          </div>`;
      })
      .join("");

    grid.innerHTML = cards || `<div class="d-empty">No categories reported yet.</div>`;

    document.getElementById("catSummaryTotal").textContent = totalReported;
    document.getElementById("catSummaryResolved").textContent = totalResolved;
    document.getElementById("catSummaryOpen").textContent = Math.max(0, totalReported - totalResolved);
    document.getElementById("catSummaryRate").textContent =
      totalReported > 0 ? `${Math.round((totalResolved / totalReported) * 100)}%` : "–";
  } catch (e) {
    grid.innerHTML = `<div class="d-empty">Couldn't load category counts right now.</div>`;
  }
}

// ---- List + filtering ----
function applyFilters() {
  return allComplaints.filter((c) => {
    if (activeLevelFilter && c.priority_level !== activeLevelFilter) return false;
    if (activeStatusFilter && c.status !== activeStatusFilter) return false;
    return true;
  });
}

function renderList() {
  const list = applyFilters();
  const container = document.getElementById("complaintList");
  if (list.length === 0) {
    container.innerHTML = `<div class="d-empty">No incidents match this filter.</div>`;
    renderMarkers([]);
    return;
  }
  container.innerHTML = list
    .map(
      (c) => `
    <div class="d-row" data-id="${c.id}">
      <div class="stripe" style="background:${PRIORITY_COLORS[c.priority_level]}"></div>
      <div class="body">
        <div class="top">
          <span class="cat">${c.category}</span>
          <span class="score" style="color:${PRIORITY_COLORS[c.priority_level]}">${c.priority_score}</span>
        </div>
        <div class="meta">${c.department} · ${c.affected_citizens} affected · ${timeAgo(c.created_at)}</div>
        <div class="id">${c.id}</div>
      </div>
    </div>`
    )
    .join("");

  container.querySelectorAll(".d-row").forEach((row) => {
    row.addEventListener("click", () => openDetail(row.dataset.id));
  });

  renderMarkers(list);
}

function timeAgo(iso) {
  const diffMs = Date.now() - new Date(iso).getTime();
  const h = Math.floor(diffMs / 3600000);
  if (h < 1) return "just now";
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function formatFullDate(iso) {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

// ---- Stat strip filter clicks ----
document.querySelectorAll(".d-stat").forEach((el) => {
  el.addEventListener("click", () => {
    const lvl = el.dataset.level;
    if (lvl === "__affected") return;
    document.querySelectorAll(".d-stat").forEach((s) => s.classList.remove("active"));
    activeLevelFilter = lvl;
    if (lvl) el.classList.add("active");
    renderList();
  });
});

document.querySelectorAll(".d-filter-chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    document.querySelectorAll(".d-filter-chip").forEach((c) => c.classList.remove("active"));
    chip.classList.add("active");
    activeStatusFilter = chip.dataset.status;
    renderList();
  });
});

// ---- Detail panel ----
async function openDetail(id) {
  const res = await fetch(`${API}/api/complaints/${id}`);
  if (!res.ok) return;
  const c = await res.json();
  renderDetail(c);
}

function factorBar(c, meta) {
  const val = c[meta.key] ?? 0;
  const color = val >= 76 ? "#C1392B" : val >= 51 ? "#E0912B" : val >= 26 ? "#2E6E8E" : "#5C7A63";
  return `
    <div class="d-factor">
      <div class="top"><span class="name">${meta.label}</span><span class="val">${val.toFixed(1)}</span></div>
      <div class="bar-track"><div class="bar-fill" style="width:${Math.min(val,100)}%; background:${color}"></div></div>
      <div class="weight">weight ${(meta.weight * 100).toFixed(0)}%  ·  contributes ${(val * meta.weight).toFixed(1)} pts</div>
    </div>`;
}

function renderDetail(c) {
  const overlay = document.getElementById("detailOverlay");
  // Show the panel FIRST (single atomic class toggle, can't fail), then build and
  // insert its content. This ordering means even if something below throws, the
  // overlay is already correctly positioned full-screen — it just won't have content
  // yet — instead of the old failure mode where an error could skip the positioning
  // step entirely and the panel would render as a plain block "below the map".
  overlay.classList.add("open");

  const levelColor = PRIORITY_COLORS[c.priority_level];

  const statuses = ["RECEIVED", "ASSIGNED", "IN_PROGRESS", "RESOLVED"];
  const statusBtns = statuses
    .map(
      (s) =>
        `<button class="d-status-btn ${s === c.status ? "current" : ""}" data-status="${s}" data-id="${c.id}">${s.replace("_", " ")}</button>`
    )
    .join("");

  const landmarks = (c.nearby_landmarks || [])
    .map((l) => `<div class="d-landmark"><span class="name">${l.name} <span style="color:#8FA3B5">(${l.kind})</span></span><span class="dist">${l.distance_m}m</span></div>`)
    .join("") || `<div class="d-linked">No critical facilities within 300m.</div>`;

  const linked = (c.linked_reports || []);
  const linkedHtml = linked.length
    ? `<div class="d-section-label">Linked reports (${linked.length})</div><div class="d-landmarks">${linked
        .map((l) => `<div class="d-landmark"><span class="name">${l.id}</span><span class="dist">${timeAgo(l.created_at)}</span></div>`)
        .join("")}</div>`
    : "";

  overlay.innerHTML = `
    <div class="d-detail">
      <button class="d-detail-close" id="closeDetail">&larr; Close</button>
      <div class="d-detail-badges">
        <span class="badge ${(c.priority_level || "low").toLowerCase()}">${c.priority_level} · ${c.priority_score}/100</span>
        <span class="badge" style="color:#8FA3B5; background:#16283A;">${(c.status || "").replace("_"," ")}</span>
      </div>
      <h2>${c.category}</h2>
      <div class="id mono">${c.id} · ${c.address || ""}</div>

      ${c.image_path ? `<div class="d-photo"><img src="/uploads/${c.image_path.split(/[\\/]/).pop()}" onerror="this.parentElement.remove()"></div>` : ""}

      <div class="d-info-grid" style="margin-top:14px;">
        <div class="d-info-item"><div class="l">Affected citizens</div><div class="v">${c.affected_citizens}</div></div>
        <div class="d-info-item"><div class="l">Department</div><div class="v" style="font-size:12px;">${c.department}</div></div>
        <div class="d-info-item"><div class="l">SLA target</div><div class="v">${formatSla(c.sla_hours)}</div></div>
        <div class="d-info-item"><div class="l">Reported</div><div class="v" style="font-size:12px;">${timeAgo(c.created_at)}</div></div>
      </div>

      <div class="d-section-label">Registered by</div>
      <div class="d-info-grid">
        <div class="d-info-item"><div class="l">Citizen</div><div class="v" style="font-size:12px;">${c.reporter_name || (c.reporter_id && c.reporter_id !== "anonymous" ? c.reporter_id : "Anonymous")}</div></div>
        <div class="d-info-item"><div class="l">Registered at</div><div class="v" style="font-size:12px;">${formatFullDate(c.created_at)}</div></div>
      </div>

      <div class="d-section-label">CV verification</div>
      <div class="d-cv-note">
        <b style="color:${c.cv_valid ? "#6FD1C8" : "#E0912B"}">${c.cv_valid ? "Verified" : "Needs manual review"}</b> ·
        detected "${c.detected_class || "n/a"}" at ${((c.cv_confidence || 0)*100).toFixed(0)}% confidence,
        ${c.defect_count || 0} defect(s), ${c.damage_area_pct || 0}% damage area.<br>${c.cv_notes || ""}
      </div>

      <div class="d-section-label">Priority score breakdown</div>
      ${FACTOR_META.map((m) => factorBar(c, m)).join("")}
      <div class="d-total">
        <span class="label">Weighted total</span>
        <span class="score" style="color:${levelColor}">${c.priority_score}</span>
      </div>

      <div class="d-section-label">Nearby critical facilities</div>
      <div class="d-landmarks">${landmarks}</div>

      ${linkedHtml}

      <div class="d-section-label">Update status <span style="text-transform:none; letter-spacing:0; color:var(--dash-text-dim); font-weight:400;">(the citizen is notified automatically on any change)</span></div>
      <div class="d-status-actions">${statusBtns}</div>

      ${c.description ? `<div class="d-section-label">Citizen description</div><div class="d-cv-note">${c.description}</div>` : ""}
    </div>
  `;

  document.getElementById("closeDetail").addEventListener("click", closeDetail);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) closeDetail(); });

  overlay.querySelectorAll(".d-status-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (btn.classList.contains("current")) return;
      const newStatus = btn.dataset.status;
      const fd = new FormData();
      fd.append("status", newStatus);
      const res = await fetch(`${API}/api/complaints/${btn.dataset.id}/status`, {
        method: "PATCH",
        headers: GovAuth.authHeaders(),
        body: fd,
      });
      if (res.status === 401) {
        GovAuth.clearSession();
        window.location.href = "/gov-login.html";
        return;
      }
      if (!res.ok) {
        showToast("Couldn't update status — please try again.");
        return;
      }
      const updated = await res.json();
      if (updated.citizen_notified) {
        showToast(
          newStatus === "RESOLVED"
            ? `Marked resolved — citizen notified.`
            : `Status updated — citizen notified.`
        );
      } else {
        showToast("Status updated.");
      }
      await refresh();
      openDetail(c.id);
    });
  });
}

function closeDetail() {
  const overlay = document.getElementById("detailOverlay");
  overlay.classList.remove("open");
  setTimeout(() => map && map.invalidateSize(), 50);
}

// ---- Load ----
async function refresh() {
  const res = await fetch(`${API}/api/complaints?sort=priority_desc`);
  allComplaints = await res.json();
  renderList();
  await loadStats();
  if (currentView === "departments") await loadDepartments();
  else if (currentView === "categories") await loadCategories();
}

initOfficerBadge();
initMap();
refresh();
setInterval(refresh, 8000); // side-by-side sync: picks up new citizen-filed complaints automatically
