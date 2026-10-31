(function () {
    "use strict";
    if (!/(?:^|[?&])calibrate=1(?:&|$)/.test(window.location.search)) return;

    var overlay = document.createElement("section");
    overlay.setAttribute("aria-labelledby", "ruler-title");
    overlay.style.cssText = "position:fixed;top:0;right:0;bottom:0;left:0;z-index:10000;overflow:auto;box-sizing:border-box;background:#fff;color:#111;font:18px/1.4 system-ui,-apple-system,sans-serif;padding:20px;";
    overlay.innerHTML = '<h1 id="ruler-title" tabindex="-1" style="font-size:28px;margin:0 0 8px">Measure this tablet</h1><p id="ruler-identity" style="font-size:24px;font-weight:bold;margin:0 0 8px"></p><p id="ruler-zoom" role="status" style="font-weight:bold"></p>' +
        '<p style="max-width:45em;margin:0 0 10px">Place a physical ruler against each target and measure between the endpoint marks. Enter each measured length in millimetres in the controller.</p>' +
        '<p style="max-width:45em;margin:0 0 10px">CSS mm and device pixel ratio do not represent real physical millimetres. Remeasure after changing orientation, zoom, or display mode.</p>' +
        '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:18px"><button type="button" id="ruler-fullscreen" style="font:inherit;padding:10px 16px">Full screen</button><button type="button" id="ruler-close" style="font:inherit;padding:10px 16px">Return to display</button></div>' +
        '<div id="ruler-horizontal-label" style="font-weight:bold"></div><div id="ruler-horizontal" aria-hidden="true" style="position:relative;height:36px;margin:8px 0 16px 8px"></div>' +
        '<div id="ruler-vertical-label" style="font-weight:bold"></div><div id="ruler-vertical" aria-hidden="true" style="position:relative;width:36px;margin:8px 0 8px 8px"></div>';
    document.body.appendChild(overlay);
    var horizontal = document.getElementById("ruler-horizontal");
    var vertical = document.getElementById("ruler-vertical");
    var identity = document.getElementById("hud-identity");
    function updateIdentity() {
        document.getElementById("ruler-identity").textContent = identity ? identity.textContent : "";
    }
    updateIdentity();
    var observer = new MutationObserver(updateIdentity);
    if (identity) observer.observe(identity, { childList: true, characterData: true, subtree: true });
    function mark(parent, style) {
        var el = document.createElement("div");
        el.style.cssText = "position:absolute;background:#111;" + style;
        parent.appendChild(el);
    }
    function draw() {
        var zoomed = window.visualViewport && Math.abs(window.visualViewport.scale - 1) > 0.001;
        document.getElementById("ruler-zoom").textContent = zoomed ? "Return to 100% zoom before measuring." : "";
        horizontal.hidden = vertical.hidden = !!zoomed;
        var w = Math.max(1, Math.min(200, Math.floor(window.innerWidth - 60)));
        var h = Math.max(1, Math.min(200, Math.floor(window.innerHeight - 60)));
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
        document.getElementById("ruler-horizontal-label").textContent = "Horizontal: " + w + " CSS px between endpoints";
        document.getElementById("ruler-vertical-label").textContent = "Vertical: " + h + " CSS px between endpoints";
    }
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
        observer.disconnect();
        overlay.parentNode.removeChild(overlay);
        if (fullscreen && !fullscreen.hidden) fullscreen.focus();
    });
})();
