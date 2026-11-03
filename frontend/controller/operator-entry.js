"use strict";
(function () {
    function openWorkspace() {
        const destination = new URL("physical.html", window.location.href);
        destination.search = window.location.search;
        destination.hash = window.location.hash;
        document.getElementById("entry-link").href = destination.href;
        try { window.location.replace(destination.href); }
        catch (_) { document.getElementById("entry-status").textContent = "Automatic opening was blocked. Use Open wall workspace to continue."; }
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", openWorkspace, { once: true });
    else openWorkspace();
}());
