const API = "";

let state = {
  category: null,
  severity: null,
  photoFile: null,
  lat: null,
  lon: null,
};

// ---- Category grid ----
const grid = document.getElementById("categoryGrid");
CATEGORY_LIST.forEach((cat) => {
  const div = document.createElement("div");
  div.className = "c-cat";
  div.dataset.cat = cat;
  div.innerHTML = `${CATEGORY_ICONS[cat]}<span>${cat}</span>`;
  div.addEventListener("click", () => {
    document.querySelectorAll(".c-cat").forEach((c) => c.classList.remove("active"));
    div.classList.add("active");
    state.category = cat;
  });
  grid.appendChild(div);
});

// If the citizen picked a category on the homepage's Quick Report widget,
// carry that choice straight over here so they only need to fill in the
// remaining details (photo, description, location) instead of picking again.
(function preselectFromQuickReport() {
  let quickCat = null;
  try { quickCat = sessionStorage.getItem("jandrishti_quick_category"); } catch (e) {}
  if (!quickCat) return;
  const match = document.querySelector(`.c-cat[data-cat="${CSS.escape(quickCat)}"]`);
  if (match) {
    match.click();
    document.getElementById("description")?.focus();
  }
  try { sessionStorage.removeItem("jandrishti_quick_category"); } catch (e) {}
})();

// If logged in, submit under the account's email automatically and offer a
// quick link back to "My Reports".
(function applyLoginState() {
  if (typeof CivicAuth === "undefined") return;
  const btn = document.getElementById("myReportsBtn");
  if (CivicAuth.isLoggedIn()) {
    const user = CivicAuth.getUser();
    if (btn) { btn.textContent = "My Reports"; btn.href = "/profile.html"; }
    state.loggedInEmail = user.email;
  } else if (btn) {
    btn.textContent = "Sign In";
    btn.href = "/account.html";
  }
})();

// ---- Severity chips ----
document.querySelectorAll(".c-chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    const already = chip.classList.contains("active");
    document.querySelectorAll(".c-chip").forEach((c) => c.classList.remove("active"));
    if (!already) {
      chip.classList.add("active");
      state.severity = chip.dataset.val;
    } else {
      state.severity = null;
    }
  });
});

// ---- Photo ----
const photoInput = document.getElementById("photoInput");
const photoPreview = document.getElementById("photoPreview");
const photoPlaceholder = document.getElementById("photoPlaceholder");
const retakeTag = document.getElementById("retakeTag");

photoInput.addEventListener("change", () => {
  const file = photoInput.files[0];
  if (!file) return;
  state.photoFile = file;
  const url = URL.createObjectURL(file);
  photoPreview.src = url;
  photoPreview.classList.remove("c-hidden");
  photoPlaceholder.classList.add("c-hidden");
  retakeTag.classList.remove("c-hidden");
});

// ---- Geolocation ----
const locAddr = document.getElementById("locAddr");
const locCoords = document.getElementById("locCoords");
const locRetry = document.getElementById("locRetry");

function detectLocation() {
  locAddr.textContent = "Detecting your location…";
  locCoords.textContent = "Please allow location access";
  if (!navigator.geolocation) {
    locAddr.textContent = "Location unavailable";
    locCoords.textContent = "Your browser doesn't support geolocation";
    return;
  }
  navigator.geolocation.getCurrentPosition(
    async (pos) => {
      state.lat = pos.coords.latitude;
      state.lon = pos.coords.longitude;
      locCoords.textContent = `${state.lat.toFixed(5)}, ${state.lon.toFixed(5)}`;
      locAddr.textContent = "Location captured";
      // best-effort reverse geocode, purely cosmetic — submission doesn't depend on it
      try {
        const r = await fetch(
          `https://nominatim.openstreetmap.org/reverse?format=json&lat=${state.lat}&lon=${state.lon}&zoom=17`
        );
        const d = await r.json();
        if (d.display_name) locAddr.textContent = d.display_name;
      } catch (e) { /* fine, coords alone are enough */ }
    },
    (err) => {
      locAddr.textContent = "Couldn't get your location";
      locCoords.textContent = err.message || "Tap retry, or check location permissions";
    },
    { enableHighAccuracy: true, timeout: 8000 }
  );
}
locRetry.addEventListener("click", detectLocation);
detectLocation();

// ---- Submit ----
const form = document.getElementById("complaintForm");
const submitBtn = document.getElementById("submitBtn");
const submitLabel = document.getElementById("submitLabel");
const formError = document.getElementById("formError");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  formError.classList.add("c-hidden");

  if (!state.category) {
    showError("Please select what kind of problem this is.");
    return;
  }
  if (state.lat === null) {
    showError("We need your location to route this to the right department. Try 'Retry' above.");
    return;
  }

  submitBtn.disabled = true;
  submitBtn.classList.add("loading");
  submitLabel.textContent = "Analyzing…";

  const fd = new FormData();
  fd.append("category", state.category);
  fd.append("description", document.getElementById("description").value);
  if (state.severity) fd.append("citizen_severity", state.severity);
  fd.append("latitude", state.lat);
  fd.append("longitude", state.lon);
  if (state.photoFile) fd.append("image", state.photoFile);
  if (state.loggedInEmail) fd.append("reporter_id", state.loggedInEmail);

  const authHeaders = (typeof CivicAuth !== "undefined") ? CivicAuth.authHeaders() : {};

  try {
    const res = await fetch(`${API}/api/complaints`, { method: "POST", body: fd, headers: authHeaders });
    if (!res.ok) throw new Error(`Server returned ${res.status}`);
    const data = await res.json();
    showResult(data);
  } catch (err) {
    showError("Something went wrong submitting your report. Please try again.");
    submitBtn.disabled = false;
    submitBtn.classList.remove("loading");
    submitLabel.textContent = "Submit report";
  }
});

function showError(msg) {
  formError.textContent = msg;
  formError.classList.remove("c-hidden");
}

function showResult(data) {
  const c = data.complaint;
  document.getElementById("formView").classList.add("c-hidden");
  document.getElementById("resultView").classList.remove("c-hidden");
  document.getElementById("resultId").textContent = c.id;

  const levelColor = PRIORITY_COLORS[c.priority_level];
  const card = document.getElementById("resultCard");
  const scoreComponents = [
    ["severity_score", "Severity"],
    ["public_impact_score", "Public Impact"],
    ["safety_risk_score", "Accident / Safety Risk"],
    ["location_criticality_score", "Location Criticality"],
    ["historical_recurrence_score", "Historical Recurrence"],
    ["future_risk_score", "Future Risk"],
  ];
  card.innerHTML = `
    <div class="row"><span class="label">Category</span><span class="value">${c.category}</span></div>
    <div class="row"><span class="label">Priority level</span><span class="value" style="color:${levelColor}">${c.priority_level} (${c.priority_score}/100)</span></div>
    <div class="row"><span class="label">Assigned to</span><span class="value">${c.department}</span></div>
    <div class="row"><span class="label">Target response</span><span class="value">${formatSla(c.sla_hours)}</span></div>
    <div class="row"><span class="label">Image verification</span><span class="value">${c.cv_valid ? "Confirmed" : "Needs review"}</span></div>
    ${data.joined_existing_incident ? `<div class="row"><span class="label">Status</span><span class="value">Linked to an existing report in this area</span></div>` : ""}
    <div class="c-score-breakdown">
      <div class="c-score-breakdown-title">Score breakdown</div>
      ${scoreComponents.map(([key, label]) => `
        <div class="c-score-row">
          <span>${label}</span>
          <div class="c-score-track"><div class="c-score-fill" style="width:${Math.min(100, c[key] || 0)}%"></div></div>
          <b>${c[key] != null ? c[key] : "—"}</b>
        </div>`).join("")}
    </div>
  `;

  document.getElementById("resultNote").textContent = data.joined_existing_incident
    ? "Other citizens have already flagged this — your report increases its priority and helps the department see the real scale of the problem."
    : "Your report has been verified and scored by the priority engine. You'll be notified when the assigned department takes action.";
}

document.getElementById("reportAnother").addEventListener("click", () => location.reload());
