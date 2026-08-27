# Government Infrastructure Priority Engine

A working prototype: citizens report infrastructure problems with a photo and location,
the system verifies and scores them, and a government dashboard shows what needs
attention first — with the full reasoning behind every score visible, not hidden in a
black box.

## Quick start

```bash
cd backend
./run.sh
```

That creates a virtualenv, installs dependencies, seeds ~160 realistic demo complaints,
and starts the server at **http://localhost:8000**.

- **Landing page:** http://localhost:8000
- **Citizen login / register:** http://localhost:8000/account.html
- **Citizen report form:** http://localhost:8000/citizen.html
- **Citizen dashboard:** http://localhost:8000/citizen-dashboard.html (shown right after a citizen signs in — lists registered issues with their location and a "confirm this is real" upvote, nothing more)
- **Government portal sign-in:** http://localhost:8000/gov-login.html
- **Government dashboard:** http://localhost:8000/dashboard.html (redirects to sign-in if not logged in)
- **API docs (auto-generated):** http://localhost:8000/docs

### Citizen vs. Government login
Both `account.html` (citizen) and `gov-login.html` (government) now show a
small "Citizen Login / Government Login" switcher above the sign-in form, so
either audience can get to the right portal from either page. Picking
**Citizen Login** signs into the regular citizen account and lands on the
citizen dashboard above. Picking **Government Login** goes to the staff
sign-in and, on success, lands on the full government command-center
dashboard — nothing about that dashboard has changed.

### Government portal demo accounts
The dashboard is now staff-only, behind its own login (separate from citizen
accounts — see `officers` table / `database.seed_default_officers`). Seeded
accounts, all with password `govdemo123`:

| Email | Scope |
|---|---|
| admin@civicvoice.gov | All departments |
| roads@civicvoice.gov | Road & Infrastructure |
| electrical@civicvoice.gov | Electrical Department |
| waste@civicvoice.gov | Waste Management |
| water@civicvoice.gov | Water Supply Department |
| health@civicvoice.gov | Public Health Department |
| maintenance@civicvoice.gov | General Maintenance |

Signing in unlocks the dashboard's **Departments** tab (every department's open/
assigned/in-progress/resolved counts and active tasks) alongside the existing
**Priority Queue** map+list view, and lets you change a complaint's status.
Marking a complaint RESOLVED (or any other status change) automatically writes
an in-app notification for the citizen who filed it — visible via the bell icon
on the citizen site once they're signed in — and also sends a real email if SMTP
is configured (see `backend/.env.example`). The two sides stay in sync
automatically: the dashboard polls the shared API every few seconds, so a
complaint filed on the citizen site shows up on the government side without a
refresh.

No Postgres/PostGIS setup needed — this runs on SQLite so any teammate can `git clone`
and be running in under a minute. See "Scaling this up" below for what changes in a
real deployment.

To wipe and regenerate demo data at any point:
```bash
cd backend && python3 seed_data.py
```

## What's actually implemented (not simulated)

- **Citizen submission flow** — photo upload, category selection, description, live
  browser geolocation, reverse geocoding.
- **Computer vision verification** (`cv_module.py`) — a genuine hybrid:
  - **Relevance check (real trained model):** a real pretrained **YOLOv8** (COCO
    weights, bundled in `models/yolov8n.pt` so it works fully offline — no venue wifi
    dependency) detects whether a person is filling the frame, catching the classic
    "claimed Pothole, uploaded a selfie" case with an actual trained detector instead
    of a color heuristic.
  - **Damage assessment (rule-based OpenCV):** COCO has no "pothole" or "road crack"
    class — no free pretrained model detects these. Real OpenCV edge/contour analysis
    (potholes/cracks) and color/clutter analysis (garbage) reads actual pixel data to
    estimate damage type, defect count, and area. This is honestly Phase 1 from the
    spec, not a trained model — see the roadmap table below for what a fine-tuned
    detector would need.
- **Transparent weighted Priority Engine** (`priority_engine.py`) — the exact formula
  from the spec:
  ```
  Priority = 0.30·Severity + 0.20·PublicImpact + 0.15·SafetyRisk
           + 0.15·LocationCriticality + 0.10·HistoricalRecurrence + 0.10·FutureRisk
  ```
  Every sub-score is computed from an inspectable rule (see the file — each function
  is ~10 lines and documented). The dashboard shows this full breakdown per complaint,
  including each factor's weight and point contribution, so an official can see exactly
  why something is Critical instead of trusting a black box.
- **Duplicate/incident clustering** (`duplicate_detection.py`) — reports of the same
  category within 200m and 45 days merge into one incident instead of creating N
  separate tasks, and the incident's priority score is **recomputed upward** as more
  citizens report it (more affected citizens is real signal).
- **Location intelligence** (`geo_utils.py`) — haversine distance to a real set of
  seeded landmarks (schools, hospitals, bus stops, markets, intersections), which
  drives location-criticality and safety-risk scoring.
- **Department auto-routing and SLA assignment** based on category.
- **Live government dashboard** — dark command-center UI, map with priority-colored
  markers, filterable priority queue, full score-breakdown detail panel, and working
  status transitions (Received → Assigned → In Progress → Resolved).

## What's deliberately NOT implemented — roadmap, not hidden gaps

We scoped this on purpose rather than faking the hardest parts. Say this out loud in
the pitch — it reads as engineering judgement, not incompleteness.

| Feature | Status | Why |
|---|---|---|
| Fine-tuned pothole/road-damage detector | Not implemented | A pretrained *general-object* YOLOv8 is real and running (see above) — but no free model detects "pothole" specifically. Training one needs labeled data (RDD2022, Roboflow pothole sets) and GPU time we didn't have. `cv_module.py`'s damage functions are written so a fine-tuned model is a drop-in replacement. |
| Predictive/time-series future-risk forecasting | Simplified to a heuristic | A real forecast needs historical *resolution outcome* data we don't have yet. `compute_future_risk()` is honestly labeled as a proxy, not a trained model — claiming otherwise to judges would be the fastest way to lose credibility. |
| Field worker mobile app | Not built | Downstream of the core innovation (the priority engine). Status can already be updated from the dashboard as a stand-in. |
| Before/after AI repair verification | Not built | Real version needs a trained image-similarity/damage-absence model. |
| Citizen feedback loop / auto-reopen | Not built | Straightforward to add once resolution flow exists — designed for, not implemented. |
| Full auth/RBAC/JWT/audit logs | Not built | Correct instinct for production; not what a hackathon demo is judged on. |
| PostgreSQL + PostGIS | Using SQLite + haversine instead | Same spatial logic, zero setup friction. Swappable later (see below). |

## Architecture

```
Citizen (citizen.html)
   │  photo + category + description + GPS
   ▼
POST /api/complaints  (main.py)
   │
   ├─ CV analysis (cv_module.py) — OpenCV edge/contour/color heuristics
   ├─ Reverse geocoding (geo_utils.py) — OpenStreetMap Nominatim
   ├─ Location criticality (geo_utils.py) — distance to seeded landmarks
   ├─ Duplicate/incident clustering (duplicate_detection.py)
   ├─ Priority Engine (priority_engine.py) — weighted scoring → Critical/High/Medium/Low
   └─ SQLite (schema.sql)
   ▼
GET /api/complaints, /api/stats, /api/complaints/{id}
   ▼
Government Dashboard (dashboard.html) — map, priority queue, score breakdown, status control
```

## Project structure

```
backend/
  main.py                 FastAPI app — all API routes + static file serving
  database.py              SQLite connection + landmark seeding
  schema.sql                Table definitions
  priority_engine.py       The weighted scoring formula (read this first)
  cv_module.py              OpenCV-based image verification
  geo_utils.py               Haversine distance, location criticality, reverse geocoding
  duplicate_detection.py    Incident clustering logic
  seed_data.py                Generates realistic demo data through the REAL scoring engine
  requirements.txt
  run.sh                        One-command start
  static/
    index.html                 Landing page
    citizen.html                Citizen report form
    dashboard.html          Government command-center dashboard
    css/                         tokens.css (shared design system), citizen.css, dashboard.css
    js/                            categories.js (shared), citizen.js, dashboard.js
  uploads/                    Citizen-submitted photos land here
```

## Team division (suggested — adjust to who's already touched what)

1. **CV/AI** — improve `cv_module.py`, or attempt a real pretrained pothole-detection
   model swap-in (Roboflow Universe has several pretrained pothole/road-damage YOLO
   models) as a stretch goal.
2. **Backend** — `main.py`, new endpoints, auth if you have time.
3. **Priority Engine** — tune `priority_engine.py` weights/formulas, extend
   `duplicate_detection.py`.
4. **Citizen frontend** — `citizen.html` / `citizen.css` / `citizen.js`.
5. **Dashboard frontend** — `dashboard.html` / `dashboard.css` / `dashboard.js`.
6. **Data + pitch** — tune `seed_data.py` for a compelling demo dataset, own the deck
   and the "what's real vs roadmap" slide, rehearse the live demo.

## Scaling this up (post-hackathon)

- Swap SQLite → PostgreSQL + PostGIS; `geo_utils.haversine_m` becomes a PostGIS
  `ST_Distance` query, same interface.
- Swap `cv_module.analyze_image()`'s internals for a fine-tuned YOLO model — the
  function signature and return shape are already YOLO-shaped.
- Add the Phase 2 ML priority model described in the spec: once real resolution
  outcomes exist (`was_priority_correct`, `actual_resolution_time`, etc.), train
  Random Forest/XGBoost on them and use it to replace or ensemble with the current
  transparent weighted formula.
- Add JWT/OAuth auth, RBAC per role (citizen/officer/admin/field worker), and audit
  logging before this touches real citizen data.
