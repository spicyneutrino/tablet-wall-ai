"use strict";
(function () {
    const themes = ["system", "light", "dark"];
    let theme = "system";
    try { const saved = localStorage.getItem("tablet-wall-theme"); if (themes.includes(saved)) theme = saved; } catch (_) {}
    function apply() {
        if (theme === "system") delete document.documentElement.dataset.theme;
        else document.documentElement.dataset.theme = theme;
    }
    if (theme !== "system") apply();
    document.addEventListener("DOMContentLoaded", function () {
        const toggle = document.getElementById("theme-toggle");
        function label() {
            toggle.querySelector("span").textContent = theme[0].toUpperCase() + theme.slice(1);
            toggle.setAttribute("aria-label", "Theme: " + theme + ". Switch to " + themes[(themes.indexOf(theme) + 1) % themes.length]);
        }
        label();
        toggle.addEventListener("click", function () {
            theme = themes[(themes.indexOf(theme) + 1) % themes.length];
            apply(); label();
            try { localStorage.setItem("tablet-wall-theme", theme); } catch (_) {}
        });
    }, { once: true });
}());
