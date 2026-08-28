const API = "";

// Citizen-only page — send anyone not signed in as a citizen back to the
// login page (mirrors profile.js's guard).
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

const timeAgo = (iso) => {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
};

// ---- Anonymous per-device upvote guard — same mechanism as the government
// dashboard's "Confirm this is real" button (js/dashboard.js), so a device's
// confirmations are recognized consistently across both views. ----
function getVoterKey() {
  let key = localStorage.getItem("civic_voter_key");
  if (!key) {
    key = "voter_" + Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem("civic_voter_key", key);
  }
  return key;
}
function hasVoted(complaintId) {
  const voted = JSON.parse(localStorage.getItem("civic_voted_complaints") || "[]");
  return voted.includes(complaintId);
}
function markVoted(complaintId) {
  const voted = JSON.parse(localStorage.getItem("civic_voted_complaints") || "[]");
  if (!voted.includes(complaintId)) {
    voted.push(complaintId);
    localStorage.setItem("civic_voted_complaints", JSON.stringify(voted));
  }
}

let allIssues = [];
let activeCategory = "";

async function loadIssues() {
  const list = document.getElementById("issuesList");
  try {
    const res = await fetch(`${API}/api/complaints?sort=recent&only_primary=true`);
    allIssues = await res.json();
    applyFilter();
  } catch (e) {
    list.innerHTML = `<div class="l-recent-empty">Couldn't load registered issues right now.</div>`;
  }
}

function applyFilter() {
  const filtered = activeCategory ? allIssues.filter((c) => c.category === activeCategory) : allIssues;
  renderIssues(filtered);
}

document.querySelectorAll(".cd-filter-chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    document.querySelectorAll(".cd-filter-chip").forEach((c) => c.classList.remove("active"));
    chip.classList.add("active");
    activeCategory = chip.dataset.category;
    applyFilter();
  });
});

function renderIssues(rows) {
  const list = document.getElementById("issuesList");
  if (!rows.length) {
    list.innerHTML = allIssues.length
      ? `<div class="l-recent-empty">No issues match this filter yet.</div>`
      : `<div class="l-recent-empty">No issues have been registered yet.</div>`;
    return;
  }

  list.innerHTML = rows.map((c) => {
    const level = (c.priority_level || "Low").toLowerCase();
    const loc = c.address || `${c.latitude.toFixed(4)}, ${c.longitude.toFixed(4)}`;
    const thumb = c.image_path
      ? `<img class="l-recent-thumb" src="/uploads/${c.image_path.split(/[\\/]/).pop()}" alt="">`
      : `<div class="l-recent-thumb">${CATEGORY_ICONS[c.category] || CATEGORY_ICONS["Other"]}</div>`;
    const voted = hasVoted(c.id);
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
        <div class="cd-upvote-col">
          ${c.status === "RESOLVED" ? "" : `<button class="cd-upvote-btn" data-id="${c.id}" ${voted ? "disabled" : ""}>${voted ? "Confirmed ✓" : "Confirm this is real"}</button>`}
          <span class="cd-upvote-count" id="upvoteCount-${c.id}">${c.upvotes || 0} confirmed</span>
        </div>
      </div>`;
  }).join("");

  document.querySelectorAll(".cd-upvote-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.id;
      btn.disabled = true;
      try {
        const res = await fetch(`${API}/api/complaints/${id}/upvote`, {
          method: "POST",
          headers: { "X-Voter-Key": getVoterKey() },
        });
        if (res.status === 409) {
          markVoted(id);
          btn.textContent = "Confirmed ✓";
          return;
        }
        if (!res.ok) { btn.disabled = false; return; }
        const updated = await res.json();
        markVoted(id);
        btn.textContent = "Confirmed ✓";
        const countEl = document.getElementById(`upvoteCount-${id}`);
        if (countEl) countEl.textContent = `${updated.upvotes || 0} confirmed`;
      } catch (e) {
        btn.disabled = false;
      }
    });
  });
}

loadIssues();
