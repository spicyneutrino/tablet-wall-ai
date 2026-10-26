(function () {
  "use strict";

  var THEME_KEY = "twg-theme";
  var themeToggle = document.getElementById("theme-toggle");
  var sidebar = document.getElementById("sidebar");
  var contentsToggle = document.getElementById("contents-toggle");
  var backdrop = document.getElementById("sidebar-backdrop");
  var progress = document.getElementById("reading-progress-bar");
  var dialog = document.getElementById("figure-dialog");
  var dialogArt = document.getElementById("dialog-art");
  var dialogCaption = document.getElementById("dialog-caption");
  var dialogTitle = document.getElementById("figure-dialog-title");
  var media = window.matchMedia("(prefers-color-scheme: dark)");
  var currentTheme = "auto";

  function readTheme() {
    try {
      var value = localStorage.getItem(THEME_KEY);
      return value === "light" || value === "dark" || value === "auto" ? value : "auto";
    } catch (error) {
      return "auto";
    }
  }

  function applyTheme(value, persist) {
    currentTheme = value;
    document.documentElement.dataset.themePreference = value;
    if (value === "auto") {
      delete document.documentElement.dataset.theme;
    } else {
      document.documentElement.dataset.theme = value;
    }
    if (persist) {
      try {
        localStorage.setItem(THEME_KEY, value);
      } catch (error) {
        /* the current session still updates */
      }
    }
    if (themeToggle) {
      var label = value === "auto" ? "Auto" : value === "light" ? "Light" : "Dark";
      var next = value === "auto" ? "light" : value === "light" ? "dark" : "auto";
      themeToggle.querySelector(".theme-label").textContent = label;
      themeToggle.setAttribute("aria-label", "Theme: " + label + ". Activate for " + next + ".");
    }
  }

  applyTheme(readTheme(), false);

  if (themeToggle) {
    themeToggle.addEventListener("click", function () {
      applyTheme(currentTheme === "auto" ? "light" : currentTheme === "light" ? "dark" : "auto", true);
    });
  }

  if (media && typeof media.addEventListener === "function") {
    media.addEventListener("change", function () {
      if (currentTheme === "auto") applyTheme("auto", false);
    });
  }

  function setSidebar(open) {
    if (!sidebar || !contentsToggle) return;
    sidebar.dataset.open = open ? "true" : "false";
    sidebar.inert = !open;
    contentsToggle.setAttribute("aria-expanded", open ? "true" : "false");
    if (backdrop) backdrop.hidden = !open;
    document.body.classList.toggle("nav-open", open);
    if (open) {
      var first = sidebar.querySelector(".nav-link");
      if (first) first.focus({ preventScroll: true });
    } else if (document.activeElement && sidebar.contains(document.activeElement)) {
      contentsToggle.focus({ preventScroll: true });
    }
  }

  function syncSidebarMode() {
    if (!sidebar) return;
    var mobile = window.matchMedia("(max-width: 1080px)").matches;
    if (!mobile) {
      sidebar.inert = false;
      sidebar.dataset.open = "false";
      if (contentsToggle) contentsToggle.setAttribute("aria-expanded", "false");
      if (backdrop) backdrop.hidden = true;
      document.body.classList.remove("nav-open");
    } else if (sidebar.dataset.open !== "true") {
      sidebar.inert = true;
    }
  }

  syncSidebarMode();

  if (contentsToggle) {
    contentsToggle.addEventListener("click", function () {
      setSidebar(sidebar.dataset.open !== "true");
    });
  }

  if (backdrop) {
    backdrop.addEventListener("click", function () {
      setSidebar(false);
    });
  }

  document.querySelectorAll(".nav-link").forEach(function (link) {
    link.addEventListener("click", function () {
      if (window.matchMedia("(max-width: 1080px)").matches) setSidebar(false);
    });
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && sidebar && sidebar.dataset.open === "true") {
      setSidebar(false);
    }
  });

  window.addEventListener("resize", syncSidebarMode);

  var links = Array.prototype.slice.call(document.querySelectorAll(".nav-link"));
  var chapters = Array.prototype.slice.call(document.querySelectorAll(".chapter"));
  var activeNumber = null;

  function setActive(number) {
    if (number === activeNumber) return;
    activeNumber = number;
    links.forEach(function (link) {
      if (link.dataset.chapter === number) link.setAttribute("aria-current", "true");
      else link.removeAttribute("aria-current");
    });
  }

  if ("IntersectionObserver" in window && chapters.length) {
    var observer = new IntersectionObserver(function (entries) {
      var visible = entries.filter(function (entry) { return entry.isIntersecting; });
      if (!visible.length) return;
      visible.sort(function (a, b) { return a.boundingClientRect.top - b.boundingClientRect.top; });
      setActive(visible[0].target.dataset.chapter);
    }, { rootMargin: "-18% 0px -68% 0px", threshold: 0 });
    chapters.forEach(function (chapter) { observer.observe(chapter); });
  }

  var progressFrame = null;
  function updateProgress() {
    progressFrame = null;
    if (!progress) return;
    var height = document.documentElement.scrollHeight - window.innerHeight;
    var ratio = height > 0 ? Math.min(1, Math.max(0, window.scrollY / height)) : 0;
    progress.style.width = (ratio * 100).toFixed(2) + "%";
  }
  window.addEventListener("scroll", function () {
    if (progressFrame === null) progressFrame = window.requestAnimationFrame(updateProgress);
  }, { passive: true });
  updateProgress();

  function syncTables() {
    document.querySelectorAll(".table-wrap").forEach(function (wrap) {
      var scrolls = wrap.scrollWidth > wrap.clientWidth + 1;
      wrap.classList.toggle("is-scrollable", scrolls);
      if (!scrolls) {
        wrap.removeAttribute("tabindex");
        wrap.removeAttribute("role");
        wrap.removeAttribute("aria-label");
        return;
      }
      var first = wrap.querySelector("th");
      var label = first ? first.textContent.trim() : "Table";
      wrap.tabIndex = 0;
      wrap.setAttribute("role", "region");
      wrap.setAttribute("aria-label", "Scrollable table: " + label);
    });
  }

  syncTables();
  window.addEventListener("resize", syncTables);

  document.querySelectorAll("pre").forEach(function (pre) {
    var button = document.createElement("button");
    button.className = "copy-code";
    button.type = "button";
    button.textContent = "Copy";
    button.addEventListener("click", function () {
      var code = pre.querySelector("code");
      var text = code ? code.innerText : pre.innerText;
      function done(ok) {
        button.textContent = ok ? "Copied" : "Copy failed";
        window.setTimeout(function () { button.textContent = "Copy"; }, 1500);
      }
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(function () { done(true); }, function () { done(false); });
      } else {
        try {
          var area = document.createElement("textarea");
          area.value = text;
          area.setAttribute("readonly", "");
          area.style.position = "fixed";
          area.style.opacity = "0";
          document.body.appendChild(area);
          area.select();
          document.execCommand("copy");
          document.body.removeChild(area);
          done(true);
        } catch (error) {
          done(false);
        }
      }
    });
    pre.appendChild(button);
  });

  function rewriteIds(svg) {
    var suffix = "-dialog";
    var oldIds = [];
    svg.querySelectorAll("[id]").forEach(function (node) {
      oldIds.push(node.id);
      node.id = node.id + suffix;
    });
    svg.querySelectorAll("*").forEach(function (node) {
      Array.prototype.forEach.call(node.attributes, function (attribute) {
        oldIds.forEach(function (id) {
          attribute.value = attribute.value.split("#" + id).join("#" + id + suffix);
        });
      });
    });
  }

  function openFigure(button) {
    if (!dialog || !dialogArt) return;
    var svg = button.querySelector("svg");
    if (!svg) return;
    var figure = button.closest(".figure");
    var caption = figure ? figure.querySelector("figcaption") : null;
    var clone = svg.cloneNode(true);
    rewriteIds(clone);
    dialogArt.replaceChildren(clone);
    if (dialogCaption && caption) {
      var captionClone = caption.cloneNode(true);
      var numberNode = captionClone.querySelector(".figure-number");
      if (numberNode) numberNode.remove();
      dialogCaption.textContent = captionClone.textContent.replace(/\s+/g, " ").trim();
    }
    if (dialogTitle && caption) {
      var number = caption.querySelector(".figure-number");
      dialogTitle.textContent = number ? number.textContent : "Figure";
    }
    document.body.classList.add("dialog-open");
    dialog.showModal();
    var close = dialog.querySelector("button");
    if (close) close.focus();
  }

  document.querySelectorAll(".figure-zoom").forEach(function (button) {
    button.addEventListener("click", function () { openFigure(button); });
  });

  if (dialog) {
    dialog.addEventListener("close", function () {
      document.body.classList.remove("dialog-open");
      dialogArt.replaceChildren();
    });
    dialog.addEventListener("click", function (event) {
      if (event.target === dialog) dialog.close();
    });
  }
}());
