// Global light/dark theme toggle. Applies to every page that includes this
// script and has a button with [data-theme-toggle] somewhere in its header
// (index.html, citizen.html, citizen-dashboard.html, profile.html,
// dashboard.html). Preference is stored in localStorage and shared across
// the whole site — switching pages keeps the theme you picked.
//
// NOTE: the actual attribute-setting on <html> also happens inline in each
// page's <head>, BEFORE the stylesheets load, so there's no flash of the
// wrong theme on page load. This script only needs to keep it in sync after
// that and wire up the toggle button click.
const CivicTheme = {
  KEY: "civic_theme",

  get() {
    try {
      return localStorage.getItem(this.KEY) || "light";
    } catch (e) {
      return "light";
    }
  },

  set(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(this.KEY, theme);
    } catch (e) {}
    document.querySelectorAll("[data-theme-toggle]").forEach((btn) => {
      btn.setAttribute("aria-pressed", String(theme === "dark"));
      btn.setAttribute("aria-label", theme === "dark" ? "Switch to light mode" : "Switch to dark mode");
    });
    document.dispatchEvent(new CustomEvent("civic-theme-change", { detail: { theme } }));
  },

  toggle() {
    this.set(this.get() === "dark" ? "light" : "dark");
  },

  init() {
    this.set(this.get()); // make sure attribute + button labels match storage
    document.querySelectorAll("[data-theme-toggle]").forEach((btn) => {
      btn.addEventListener("click", () => this.toggle());
    });
  },
};

CivicTheme.init();
