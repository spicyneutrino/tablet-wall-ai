// Final mockup: shared data and wall renderer. Geometry in millimetres, like the physical layout.
// Panel sizes follow published specs; bezels are illustrative.
var Q = new URLSearchParams(location.search);
var STATE = Q.get('state') || 'main';
var SHOT = !!Q.get('shot');
var IMG = '../../../assets/EXLENT_Cohort_3_Flyer_Temp.png';
var DEV = [
  { id: 't1', n: 1, name: 'Tablet 1', model: 'Pixel C', active: [211.1, 148.4], body: [242.1, 179.0] },
  { id: 't2', n: 2, name: 'Tablet 2', model: 'iPad Air 2', active: [197.1, 147.8], body: [240.0, 169.5] },
  { id: 't3', n: 3, name: 'Tablet 3', model: 'iPad mini 4', active: [159.6, 119.7], body: [203.2, 134.8] },
  { id: 't4', n: 4, name: 'Tablet 4', model: 'iPad mini 2', active: [159.6, 119.7], body: [200.0, 134.7] }
];
var LAYOUTS = {
  grid: { t1: [121.05, 89.5, 0], t2: [383.1, 89.5, 0], t3: [101.6, 266.4, 0], t4: [363.1, 266.4, 0] },
  // what another operator applied during a conflict: Tablet 3 moved 40 mm right
  grid2: { t1: [121.05, 89.5, 0], t2: [383.1, 89.5, 0], t3: [141.6, 266.4, 0], t4: [363.1, 266.4, 0] },
  stagger: { t1: [121.05, 99.5, 0], t2: [352, 130, 90], t3: [118, 302, 0], t4: [348, 330, -6] }
};
var NS = 'http://www.w3.org/2000/svg';
function el(tag, attrs, parent) { var e = document.createElementNS(NS, tag); for (var k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; }
function txt(parent, x, y, size, str, attrs) {
  var a = { x: x, y: y, 'font-size': size, 'font-weight': 700, 'font-family': 'Atkinson Hyperlegible Next, system-ui, sans-serif', fill: 'var(--stage-text)' };
  for (var k in attrs || {}) a[k] = attrs[k];
  var t = el('text', a, parent); t.textContent = str; return t;
}
function corners(cx, cy, w, h, a) {
  var r = a * Math.PI / 180, c = Math.cos(r), s = Math.sin(r);
  return [[-w / 2, -h / 2], [w / 2, -h / 2], [w / 2, h / 2], [-w / 2, h / 2]].map(function (p) { return [cx + p[0] * c - p[1] * s, cy + p[0] * s + p[1] * c]; });
}
function bounds(layout, pad) {
  var xs = [], ys = [];
  DEV.forEach(function (d) { var p = layout[d.id]; corners(p[0], p[1], d.body[0], d.body[1], p[2]).forEach(function (q) { xs.push(q[0]); ys.push(q[1]); }); });
  return { x: Math.min.apply(0, xs) - pad, y: Math.min.apply(0, ys) - pad, w: Math.max.apply(0, xs) - Math.min.apply(0, xs) + 2 * pad, h: Math.max.apply(0, ys) - Math.min.apply(0, ys) + 2 * pad };
}
var uid = 0;
// opts: layout, selected (id), edit (id: on-canvas handles), measure (id), ruler (bool, with measure),
// offline (ids), outline ('preview'), dim, label ('full'|'number'), empty, loading, aria
function renderStage(host, opts) {
  opts = opts || {};
  var off = opts.offline || [];
  var L = LAYOUTS[opts.layout || 'grid'];
  var B = bounds(LAYOUTS.stagger, 6), G = bounds(LAYOUTS.grid, 6);
  // one scale for every layout (the larger of the two), centred on the layout shown,
  // so tablets keep their drawn size when the preview switches between layouts
  var W = bounds(L, 6), pad = 26;
  var fw = Math.max(B.w, G.w) + 2 * pad, fh = Math.max(B.h, G.h) + 2 * pad;
  var vb = { x: W.x + W.w / 2 - fw / 2, y: W.y + W.h / 2 - fh / 2, w: fw, h: fh };
  host.innerHTML = '';
  var id = 'w' + (++uid);
  var svg = el('svg', { viewBox: [vb.x, vb.y, vb.w, vb.h].join(' '), role: 'img', 'aria-label': opts.aria || 'Wall preview', preserveAspectRatio: 'xMidYMid meet' }, host);
  var defs = el('defs', {}, svg);
  var pat = el('pattern', { id: id + 'h', width: 8, height: 8, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)' }, defs);
  el('rect', { width: 8, height: 8, fill: 'var(--stage-body)' }, pat);
  el('line', { x1: 0, y1: 0, x2: 0, y2: 8, stroke: 'var(--stage-hatch)', 'stroke-width': 4 }, pat);
  var clip = el('clipPath', { id: id + 'c' }, defs);
  if (opts.empty || opts.loading) {
    el('rect', { x: G.x, y: G.y, width: G.w, height: G.h, rx: 6, fill: 'none', stroke: 'var(--stage-line)', 'stroke-dasharray': '6 6', 'vector-effect': 'non-scaling-stroke' }, svg);
    if (opts.loading) DEV.forEach(function (d) { var p = LAYOUTS.grid[d.id]; el('rect', { x: p[0] - d.body[0] / 2, y: p[1] - d.body[1] / 2, width: d.body[0], height: d.body[1], rx: 10, fill: 'var(--stage-body)', class: 'skel-pulse' }, svg); });
    return svg;
  }
  if (opts.outline === 'preview') el('rect', { x: W.x, y: W.y, width: W.w, height: W.h, rx: 4, fill: 'none', stroke: 'var(--stage-sel)', 'stroke-width': 1.5, 'stroke-dasharray': '8 6', 'vector-effect': 'non-scaling-stroke' }, svg);
  var groups = [];
  DEV.forEach(function (d) {
    var p = L[d.id];
    var g = el('g', { transform: 'translate(' + p[0] + ' ' + p[1] + ') rotate(' + p[2] + ')', 'data-id': d.id }, svg);
    el('rect', { x: -d.body[0] / 2, y: -d.body[1] / 2, width: d.body[0], height: d.body[1], rx: 10, fill: 'var(--stage-body)', stroke: 'var(--stage-line)', 'vector-effect': 'non-scaling-stroke' }, g);
    if (off.indexOf(d.id) < 0) {
      var cr = el('rect', { x: -d.active[0] / 2, y: -d.active[1] / 2, width: d.active[0], height: d.active[1] }, clip);
      cr.setAttribute('transform', 'translate(' + p[0] + ' ' + p[1] + ') rotate(' + p[2] + ')');
    }
    groups.push([d, g, p]);
  });
  if (opts.pattern === 'grid') {
    var pg = el('g', { 'clip-path': 'url(#' + id + 'c)' }, svg);
    el('rect', { x: W.x, y: W.y, width: W.w, height: W.h, fill: 'var(--stage-screen)' }, pg);
    for (var gx = Math.floor(W.x / 25) * 25; gx < W.x + W.w; gx += 25) el('line', { x1: gx, y1: W.y, x2: gx, y2: W.y + W.h, stroke: 'var(--stage-text)', 'stroke-width': gx % 100 ? 0.5 : 1.25, 'vector-effect': 'non-scaling-stroke' }, pg);
    for (var gy2 = Math.floor(W.y / 25) * 25; gy2 < W.y + W.h; gy2 += 25) el('line', { x1: W.x, y1: gy2, x2: W.x + W.w, y2: gy2, stroke: 'var(--stage-text)', 'stroke-width': gy2 % 100 ? 0.5 : 1.25, 'vector-effect': 'non-scaling-stroke' }, pg);
  } else el('image', { href: IMG, x: W.x, y: W.y, width: W.w, height: W.h, preserveAspectRatio: 'xMidYMid slice', 'clip-path': 'url(#' + id + 'c)', opacity: opts.dim ? 0.35 : 1 }, svg);
  groups.forEach(function (it) {
    var d = it[0], p = it[2];
    var g = el('g', { transform: 'translate(' + p[0] + ' ' + p[1] + ') rotate(' + p[2] + ')' }, svg);
    var aw = d.active[0], ah = d.active[1];
    if (off.indexOf(d.id) >= 0) el('rect', { x: -aw / 2, y: -ah / 2, width: aw, height: ah, fill: 'url(#' + id + 'h)', stroke: 'var(--stage-warn)', 'stroke-dasharray': '6 5', 'vector-effect': 'non-scaling-stroke' }, g);
    else el('rect', { x: -aw / 2, y: -ah / 2, width: aw, height: ah, fill: 'none', stroke: 'var(--stage-line)', 'vector-effect': 'non-scaling-stroke' }, g);
    if (opts.measure === d.id) el('rect', { x: -aw / 2, y: -ah / 2, width: aw, height: ah, fill: 'var(--stage-screen)' }, g);
    it.push(g);
  });
  var k = 1;
  host._labels = function () {
    var sc = svg.getScreenCTM(); k = sc ? sc.a : 1;
    svg.querySelectorAll('.lbl,.ovl').forEach(function (n) { n.remove(); });
    var fs = 13 / k;
    // smart guide for the on-canvas edit: Tablet 2's top edge lines up with Tablet 1's
    if (opts.edit) {
      var gy = 10, gx1 = 0, gx2 = 480;
      var ov = el('g', { class: 'ovl' }, svg);
      el('line', { x1: gx1, y1: gy, x2: gx2, y2: gy, stroke: 'var(--stage-sel)', 'stroke-width': 1, 'stroke-dasharray': '3 3', 'vector-effect': 'non-scaling-stroke' }, ov);
    }
    groups.forEach(function (it) {
      var d = it[0], p = it[2], g = it[3];
      var sel = opts.selected === d.id || opts.measure === d.id || opts.edit === d.id;
      if (sel) {
        var ring = el('g', { class: 'ovl' }, g);
        var px = 4 / k;
        el('rect', { x: -d.body[0] / 2 - px, y: -d.body[1] / 2 - px, width: d.body[0] + 2 * px, height: d.body[1] + 2 * px, rx: 12, fill: 'none', stroke: 'var(--stage-sel)', 'stroke-width': opts.edit === d.id ? 1.5 : 3, 'vector-effect': 'non-scaling-stroke' }, ring);
        if (opts.edit === d.id) {
          var hw = d.body[0] / 2 + px, hh = d.body[1] / 2 + px, hs = 10 / k;
          [[-hw, -hh], [0, -hh], [hw, -hh], [hw, 0], [hw, hh], [0, hh], [-hw, hh], [-hw, 0]].forEach(function (c) {
            el('rect', { x: c[0] - hs / 2, y: c[1] - hs / 2, width: hs, height: hs, rx: 2 / k, fill: 'var(--stage-handle)', stroke: 'var(--stage-sel)', 'stroke-width': 1.5, 'vector-effect': 'non-scaling-stroke' }, ring);
          });
        }
      }
      var lg = el('g', { class: 'lbl', transform: 'rotate(' + (-p[2]) + ')' }, g);
      var rw = Math.abs(p[2]) === 90 ? d.body[1] : d.body[0], rh = Math.abs(p[2]) === 90 ? d.body[0] : d.body[1];
      var r = 11 / k, x0 = -rw / 2 + 8 / k, y0 = -rh / 2 + 8 / k;
      var compact = opts.label === 'number' || k < 0.9;
      var tw = compact ? 0 : (d.name.length * fs * 0.56 + 10 / k);
      el('rect', { x: x0, y: y0, width: 2 * r + tw, height: 2 * r, rx: r, fill: 'var(--stage-pill)', stroke: sel ? 'var(--stage-sel)' : 'var(--stage-line)', 'vector-effect': 'non-scaling-stroke' }, lg);
      txt(lg, x0 + r, y0 + r + fs * 0.36, fs, d.n, { 'text-anchor': 'middle', class: 'stage-text' });
      if (!compact) txt(lg, x0 + 2 * r + 2 / k, y0 + r + fs * 0.36, fs, d.name, { class: 'stage-text' });
      if (off.indexOf(d.id) >= 0) {
        var ow = 74 / k, oh = 24 / k, o = el('g', {}, lg);
        el('rect', { x: -ow / 2, y: -oh / 2, width: ow, height: oh, rx: 6 / k, fill: 'var(--stage-pill)', stroke: 'var(--stage-warn)', 'vector-effect': 'non-scaling-stroke' }, o);
        el('path', { d: 'M0 -4.5 L5 4.5 L-5 4.5 Z', fill: 'var(--stage-warn)', transform: 'translate(' + (-ow / 2 + 13 / k) + ' ' + (0.5 / k) + ') scale(' + (1 / k) + ')' }, o);
        txt(o, -ow / 2 + 23 / k, fs * 0.36, fs, 'Offline', { fill: 'var(--stage-warn)' });
      }
      if (opts.edit === d.id) {
        var top = -rh / 2 - 4 / k;
        el('line', { x1: 0, y1: top, x2: 0, y2: top - 22 / k, stroke: 'var(--stage-sel)', 'stroke-width': 1.5, 'vector-effect': 'non-scaling-stroke' }, lg);
        el('circle', { cx: 0, cy: top - 22 / k, r: 6 / k, fill: 'var(--stage-handle)', stroke: 'var(--stage-sel)', 'stroke-width': 1.5, 'vector-effect': 'non-scaling-stroke' }, lg);
        if (k >= 0.9) {
          var rt = 'x 352  y 130 mm  90°', rtw = rt.length * fs * 0.52 + 20 / k, rth = 26 / k;
          el('rect', { x: 14 / k, y: top - 22 / k - rth / 2, width: rtw, height: rth, rx: 6 / k, fill: 'var(--stage-sel)' }, lg);
          txt(lg, 14 / k + rtw / 2, top - 22 / k + fs * 0.36, fs, rt, { 'text-anchor': 'middle', fill: 'var(--stage-pill)' });
        }
      }
      if (opts.measure === d.id) {
        var A = d.active, mg = el('g', {}, lg);
        if (!opts.ruler) {
          el('line', { x1: -A[0] / 2, y1: A[1] / 2 + 14 / k, x2: A[0] / 2, y2: A[1] / 2 + 14 / k, stroke: 'var(--stage-sel)', 'stroke-width': 1.5, 'vector-effect': 'non-scaling-stroke' }, mg);
          txt(mg, 0, A[1] / 2 + 10 / k, fs, A[0].toFixed(1) + ' mm', { 'text-anchor': 'middle', fill: 'var(--stage-sel)' });
          el('line', { x1: A[0] / 2 - 14 / k, y1: -A[1] / 2, x2: A[0] / 2 - 14 / k, y2: A[1] / 2, stroke: 'var(--stage-sel)', 'stroke-width': 1.5, 'vector-effect': 'non-scaling-stroke' }, mg);
          txt(mg, A[0] / 2 - 20 / k, 0, fs, A[1].toFixed(1) + ' mm', { 'text-anchor': 'end', fill: 'var(--stage-sel)' });
        } else {
          // what the tablet itself shows during the ruler check: two labelled 200 px lines
          var lx = A[0] * 0.78, ly = A[1] * 0.7;
          el('line', { x1: -lx / 2, y1: -A[1] / 2 + 34 / k, x2: lx / 2, y2: -A[1] / 2 + 34 / k, stroke: 'var(--stage-text)', 'stroke-width': 2, 'vector-effect': 'non-scaling-stroke' }, mg);
          [-lx / 2, lx / 2].forEach(function (x) { el('line', { x1: x, y1: -A[1] / 2 + 28 / k, x2: x, y2: -A[1] / 2 + 40 / k, stroke: 'var(--stage-text)', 'stroke-width': 2, 'vector-effect': 'non-scaling-stroke' }, mg); });
          txt(mg, 0, -A[1] / 2 + 56 / k, fs, k < 0.9 ? 'A' : 'Line A, 200 px', { 'text-anchor': 'middle' });
          el('line', { x1: -A[0] / 2 + 40 / k, y1: -ly / 2 + 24 / k, x2: -A[0] / 2 + 40 / k, y2: ly / 2 + 24 / k, stroke: 'var(--stage-text)', 'stroke-width': 2, 'vector-effect': 'non-scaling-stroke' }, mg);
          [-ly / 2 + 24 / k, ly / 2 + 24 / k].forEach(function (y) { el('line', { x1: -A[0] / 2 + 34 / k, y1: y, x2: -A[0] / 2 + 46 / k, y2: y, stroke: 'var(--stage-text)', 'stroke-width': 2, 'vector-effect': 'non-scaling-stroke' }, mg); });
          txt(mg, -A[0] / 2 + 54 / k, 24 / k + fs * 0.36, fs, k < 0.9 ? 'B' : 'Line B, 200 px', {});
        }
        el('rect', { x: -A[0] / 2, y: -A[1] / 2, width: A[0], height: A[1], fill: 'none', stroke: 'var(--stage-sel)', 'stroke-dasharray': '4 4', 'vector-effect': 'non-scaling-stroke' }, mg);
      }
    });
  };
  requestAnimationFrame(host._labels);
  if (window.ResizeObserver) new ResizeObserver(function () { host._labels(); }).observe(host);
  return svg;
}
// Keep only the nodes for the active state: duplicate ids, headings and landmarks from other
// states never reach the DOM, so axe and the contrast walk see exactly one screen.
function inList(list, state) { return list.split(' ').some(function (t) { return t === state || (t.slice(-1) === '*' && state.indexOf(t.slice(0, -1)) === 0); }); }
function only(state) {
  document.querySelectorAll('[data-when]').forEach(function (n) { if (!inList(n.getAttribute('data-when'), state)) n.remove(); });
  document.querySelectorAll('[data-not]').forEach(function (n) { if (inList(n.getAttribute('data-not'), state)) n.remove(); });
}
