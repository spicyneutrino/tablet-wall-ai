(function () {
    "use strict";
    if (!/(?:^|[?&])calibrate=1(?:&|$)/.test(window.location.search)) return;

    var overlay = document.createElement("section");
    overlay.setAttribute("aria-labelledby", "ruler-title");
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.style.cssText = "position:fixed;top:0;right:0;bottom:0;left:0;z-index:10000;overflow:auto;box-sizing:border-box;background:#fff;color:#111;font:16px/1.4 system-ui,-apple-system,sans-serif;padding:20px;";
    overlay.innerHTML = '<h1 id="ruler-title" tabindex="-1" style="font-size:28px;margin:0 0 8px">Measure this tablet</h1><p id="ruler-identity" style="font-size:24px;font-weight:bold;margin:0 0 8px"></p><p id="ruler-zoom" role="status" style="font-weight:bold"></p>' +
        '<details style="max-width:45em;margin-bottom:10px"><summary style="min-height:32px;cursor:pointer">Measuring instructions</summary><p>Place a physical ruler against each target and measure between the endpoint marks. Enter each measured length in millimetres in the controller.</p>' +
        '<p style="max-width:45em;margin:0 0 10px">CSS mm and device pixel ratio do not represent real physical millimetres. Remeasure after changing orientation, zoom, or display mode.</p></details>' +
        '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:18px"><button type="button" id="ruler-fullscreen" style="font:inherit;padding:10px 16px">Full screen</button><button type="button" id="ruler-close" style="font:inherit;padding:10px 16px">Return to display</button></div>' +
        '<label for="ruler-span" style="display:block;margin-bottom:12px">Target span (CSS pixels) <select id="ruler-span" style="font:inherit;min-height:44px;max-width:100%"><option value="long">Long span, fits usable screen</option><option value="short">200 px short-span / higher extrapolation</option></select></label>' +
        '<div id="ruler-targets" style="position:relative;min-height:140px"><div id="ruler-horizontal-label" style="font-weight:bold"></div><div id="ruler-horizontal" aria-hidden="true" style="position:absolute;left:8px;top:24px;height:36px"></div>' +
        '<div id="ruler-vertical-label" style="position:absolute;left:52px;top:82px;right:0;font-weight:bold"></div><div id="ruler-vertical" aria-hidden="true" style="position:absolute;left:8px;top:86px;width:36px"></div></div>';
    document.body.appendChild(overlay);
    overlay.addEventListener("keydown", function (event) {
        if (event.key !== "Tab") return;
        var controls = Array.prototype.filter.call(overlay.querySelectorAll("button, select, summary"), function (el) {
            return !el.hidden && !el.disabled;
        });
        var first = controls[0];
        var last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault(); last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault(); first.focus();
        }
    });
    var horizontal = document.getElementById("ruler-horizontal");
    var vertical = document.getElementById("ruler-vertical");
    var identity = document.getElementById("hud-identity");
    function updateIdentity() {
        document.getElementById("ruler-identity").textContent = identity ? identity.textContent : "";
        if (targets) draw();
    }
    updateIdentity();
    var observer = new MutationObserver(updateIdentity);
    if (identity) observer.observe(identity, { childList: true, characterData: true, subtree: true });
    function mark(parent, style) {
        var el = document.createElement("div");
        el.style.cssText = "position:absolute;background:#111;" + style;
        parent.appendChild(el);
    }
    var targets = document.getElementById("ruler-targets");
    var span = document.getElementById("ruler-span");
    var instructions = overlay.querySelector("details");
    instructions.addEventListener("toggle", draw);
    function draw() {
        var zoomed = window.visualViewport && Math.abs(window.visualViewport.scale - 1) > 0.001;
        document.getElementById("ruler-zoom").textContent = zoomed ? "Return to 100% zoom before measuring." : "";
        horizontal.hidden = vertical.hidden = !!zoomed;
        var top = targets.getBoundingClientRect().top + overlay.scrollTop;
        var height = Math.max(140, Math.floor(window.innerHeight - top - 24));
        targets.style.height = height + "px";
        var limit = span.value === "short" ? 200 : Infinity;
        var w = Math.max(1, Math.min(limit, Math.floor(targets.getBoundingClientRect().width - 20)));
        var h = Math.max(1, Math.min(limit, height - 96));
        horizontal.innerHTML = "";
        vertical.innerHTML = "";
        horizontal.style.width = w + "px";
        vertical.style.height = h + "px";
        mark(horizontal, "left:0;top:16px;width:" + w + "px;height:4px");
        mark(horizontal, "left:-2px;top:2px;width:4px;height:32px");
        mark(horizontal, "left:" + (w - 2) + "px;top:2px;width:4px;height:32px");
        mark(vertical, "left:16px;top:0;width:4px;height:" + h + "px");
        mark(vertical, "left:2px;top:-2px;width:32px;height:4px");
        mark(vertical, "left:2px;top:" + (h - 2) + "px;width:32px;height:4px");
        document.getElementById("ruler-horizontal-label").textContent = "Horizontal: 0 to " + w + " CSS px";
        document.getElementById("ruler-vertical-label").textContent = "Vertical: 0 to " + h + " CSS px";
    }
    span.addEventListener("change", draw);
    document.addEventListener("fullscreenchange", draw);
    document.addEventListener("webkitfullscreenchange", draw);
    draw();
    window.addEventListener("resize", draw);
    if (window.visualViewport) window.visualViewport.addEventListener("resize", draw);
    document.getElementById("ruler-title").focus();
    var fullscreen = document.getElementById("fs-toggle");
    var rulerFullscreen = document.getElementById("ruler-fullscreen");
    rulerFullscreen.hidden = !fullscreen || fullscreen.hidden;
    rulerFullscreen.addEventListener("click", function () { fullscreen.click(); });
    document.getElementById("ruler-close").addEventListener("click", function () {
        window.removeEventListener("resize", draw);
        if (window.visualViewport) window.visualViewport.removeEventListener("resize", draw);
        document.removeEventListener("fullscreenchange", draw);
        document.removeEventListener("webkitfullscreenchange", draw);
        observer.disconnect();
        overlay.parentNode.removeChild(overlay);
        if (fullscreen && !fullscreen.hidden) fullscreen.focus();
    });
})();
