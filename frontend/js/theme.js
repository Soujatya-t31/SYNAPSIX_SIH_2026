// Keeps the colour preference consistent across every citizen and government page.
(() => {
  const storageKey = "civicvoice-theme";
  const savedTheme = localStorage.getItem(storageKey);
  const dark = savedTheme ? savedTheme === "dark" : false;

  function apply(isDark) {
    document.documentElement.classList.toggle("theme-dark", isDark);
    document.body.classList.toggle("theme-dark", isDark);
    button.setAttribute("aria-pressed", String(isDark));
    button.setAttribute("aria-label", isDark ? "Switch to light mode" : "Switch to dark mode");
    button.innerHTML = isDark ? "☀ <span>Light</span>" : "◐ <span>Dark</span>";
  }

  const button = document.createElement("button");
  button.type = "button";
  button.className = "theme-toggle";
  button.addEventListener("click", () => {
    const isDark = !document.documentElement.classList.contains("theme-dark");
    localStorage.setItem(storageKey, isDark ? "dark" : "light");
    apply(isDark);
  });
  document.addEventListener("DOMContentLoaded", () => {
    document.body.append(button);
    apply(dark);
  });
})();
