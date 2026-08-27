// Shared across citizen.html and dashboard.html so both stay in sync with the backend's
// category list (GET /api/categories is the source of truth for validity; this just
// supplies icons/labels for display).

const CATEGORY_ICONS = {
  "Pothole": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><ellipse cx="12" cy="14" rx="8" ry="4"/><path d="M6 14c1-2 3.5-3 6-3s5 1 6 3"/><path d="M4 8h16"/></svg>',
  "Road Crack": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 6h18M3 18h18"/><path d="M9 6 7 10l3 2-2 4 4-1-1 4"/></svg>',
  "Broken Streetlight": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 2v6"/><path d="M8 8h8l-1.5 5h-5L8 8Z"/><path d="M12 13v9"/><path d="M8 22h8"/><path d="m17 4-2 2M7 4l2 2" stroke-dasharray="2 2"/></svg>',
  "Garbage Overflow": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M6 7h12l-1 13a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2L6 7Z"/><path d="M4 7h16M9 7V4h6v3"/><path d="M9 3.5 7 7M15 3.5l2 3.5"/></svg>',
  "Water Leakage": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11Z"/></svg>',
  "Drainage Issue": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18M15 3v18"/></svg>',
  "Damaged Footpath": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 20 10 4M14 20l6-16"/><path d="M8 12h2m4 0h2"/></svg>',
  "Traffic Signal": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="8" y="2" width="8" height="16" rx="3"/><circle cx="12" cy="6" r="1.3" fill="currentColor" stroke="none"/><circle cx="12" cy="10" r="1.3" fill="currentColor" stroke="none"/><circle cx="12" cy="14" r="1.3" fill="currentColor" stroke="none"/><path d="M12 18v4"/></svg>',
  "Public Toilet": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="5" y="3" width="14" height="18" rx="1.5"/><circle cx="9" cy="12" r="1" fill="currentColor" stroke="none"/><path d="M13 8h4M13 12h4M13 16h4"/></svg>',
  "Bridge": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 16c2-4 5-6 10-6s8 2 10 6"/><path d="M2 16h20M6 16v4M12 16v4M18 16v4"/></svg>',
  "Public Building": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 21V10l8-6 8 6v11"/><path d="M4 21h16M9 21v-6h6v6"/></svg>',
  "Other": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14.7 6.3a4 4 0 0 1-5.4 5.4L4 17v3h3l5.3-5.3a4 4 0 0 1 5.4-5.4l-2.2 2.2-2-2 2.2-2.2Z"/></svg>',
};

const CATEGORY_LIST = Object.keys(CATEGORY_ICONS);

const PRIORITY_COLORS = {
  Critical: "#C1392B",
  High: "#E0912B",
  Medium: "#2E6E8E",
  Low: "#5C7A63",
};
