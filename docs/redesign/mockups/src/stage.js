// Shared mockup data and wall renderer (identical in a.html, b.html, c.html).
// Geometry is in millimetres, like the physical layout. Sizes follow published panel specs; bezels are illustrative.
var Q = new URLSearchParams(location.search);
var STATE = Q.get('state') || 'main';
if (Q.get('shot')) document.body.classList.add('shot');
var IMG = '../../../assets/EXLENT_Cohort_3_Flyer_Temp.png';
var DEV = [
  { id: 't1', n: 1, name: 'Tablet 1', model: 'Pixel C', status: 'online', seen: 'Now', active: [211.1, 148.4], body: [242.1, 179.0], wake: 'Held' },
  { id: 't2', n: 2, name: 'Tablet 2', model: 'iPad Air 2', status: 'online', seen: 'Now', active: [197.1, 147.8], body: [240.0, 169.5], wake: 'Held' },
  { id: 't3', n: 3, name: 'Tablet 3', model: 'iPad mini 4', status: 'online', seen: 'Now', active: [159.6, 119.7], body: [203.2, 134.8], wake: 'Denied by browser' },
  { id: 't4', n: 4, name: 'Tablet 4', model: 'iPad mini 2', status: 'offline', seen: '12 min ago', active: [159.6, 119.7], body: [200.0, 134.7], wake: 'Unknown' }
];
var LAYOUTS = {
  grid: { t1: [121.05, 89.5, 0], t2: [383.1, 89.5, 0], t3: [101.6, 266.4, 0], t4: [363.1, 266.4, 0] },
  stagger: { t1: [121.05, 99.5, 0], t2: [352, 130, 90], t3: [118, 302, 0], t4: [348, 330, -6] }
};
function byId(id) { return DEV.find(function (d) { return d.id === id; }); }
function corners(cx, cy, w, h, a) {
  var r = a * Math.PI / 180, c = Math.cos(r), s = Math.sin(r);
  return [[-w / 2, -h / 2], [w / 2, -h / 2], [w / 2, h / 2], [-w / 2, h / 2]].map(function (p) { return [cx + p[0] * c - p[1] * s, cy + p[0] * s + p[1] * c]; });
}
function bounds(layout, pad) {
  var xs = [], ys = [];
  DEV.forEach(function (d) { var p = layout[d.id]; corners(p[0], p[1], d.body[0], d.body[1], p[2]).forEach(function (q) { xs.push(q[0]); ys.push(q[1]); }); });
  return { x: Math.min.apply(0, xs) - pad, y: Math.min.apply(0, ys) - pad, w: Math.max.apply(0, xs) - Math.min.apply(0, xs) + 2 * pad, h: Math.max.apply(0, ys) - Math.min.apply(0, ys) + 2 * pad };
}
var NS = 'http://www.w3.org/2000/svg';
function el(tag, attrs, parent) { var e = document.createElementNS(NS, tag); for (var k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; }
var uid = 0;
// opts: layout ('grid'|'stagger'), image (bool), selected (id), outline ('draft'|null), measure (id), dim (bool), label ('full'|'number'), empty (bool)
function renderStage(host, opts) {
  opts = opts || {};
  var L = LAYOUTS[opts.layout || 'grid'];
  var vbPad = 12;
  var B = bounds(L, 6);
  var vb = { x: B.x - vbPad, y: B.y - vbPad, w: B.w + vbPad * 2, h: B.h + vbPad * 2 };
  if (opts.frame) { var fr = opts.frame; var cxv = vb.x + vb.w / 2, cyv = vb.y + vb.h / 2; if (vb.w / vb.h < fr) { var nw = vb.h * fr; vb.x = cxv - nw / 2; vb.w = nw; } else { var nh = vb.w / fr; vb.y = cyv - nh / 2; vb.h = nh; } }
  host.innerHTML = '';
  var id = 'w' + (++uid);
  var svg = el('svg', { viewBox: [vb.x, vb.y, vb.w, vb.h].join(' '), role: 'img', 'aria-label': opts.aria || 'Wall preview', preserveAspectRatio: 'xMidYMid meet' }, host);
  var defs = el('defs', {}, svg);
  var pat = el('pattern', { id: id + 'h', width: 8, height: 8, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)' }, defs);
  el('rect', { width: 8, height: 8, fill: 'var(--stage-body)' }, pat);
  el('line', { x1: 0, y1: 0, x2: 0, y2: 8, stroke: 'var(--stage-hatch)', 'stroke-width': 4 }, pat);
  var clip = el('clipPath', { id: id + 'c' }, defs);
  if (opts.empty) {
    el('rect', { x: B.x, y: B.y, width: B.w, height: B.h, fill: 'none', stroke: 'var(--stage-line)', 'stroke-dasharray': '6 6', 'vector-effect': 'non-scaling-stroke' }, svg);
    return svg;
  }
  el('rect', { x: B.x, y: B.y, width: B.w, height: B.h, fill: 'none', stroke: opts.outline === 'draft' ? 'var(--stage-draft)' : 'var(--stage-line)', 'stroke-width': opts.outline === 'draft' ? 2 : 1, 'stroke-dasharray': opts.outline === 'draft' ? '8 6' : '0', 'vector-effect': 'non-scaling-stroke' }, svg);
  var groups = [];
  DEV.forEach(function (d) {
    var p = L[d.id];
    var g = el('g', { transform: 'translate(' + p[0] + ' ' + p[1] + ') rotate(' + p[2] + ')', 'data-id': d.id }, svg);
    el('rect', { x: -d.body[0] / 2, y: -d.body[1] / 2, width: d.body[0], height: d.body[1], rx: 10, fill: 'var(--stage-body)', stroke: 'var(--stage-line)', 'vector-effect': 'non-scaling-stroke' }, g);
    if (d.status !== 'offline') {
      var cr = el('rect', { x: -d.active[0] / 2, y: -d.active[1] / 2, width: d.active[0], height: d.active[1] }, clip);
      cr.setAttribute('transform', 'translate(' + p[0] + ' ' + p[1] + ') rotate(' + p[2] + ')');
    }
    groups.push([d, g, p]);
  });
  if (opts.image !== false) {
    el('image', { href: IMG, x: B.x, y: B.y, width: B.w, height: B.h, preserveAspectRatio: 'xMidYMid slice', 'clip-path': 'url(#' + id + 'c)', opacity: opts.dim ? 0.35 : 1 }, svg);
  } else {
    el('rect', { x: B.x, y: B.y, width: B.w, height: B.h, fill: '#0d0f13', 'clip-path': 'url(#' + id + 'c)' }, svg);
  }
  var k = 1;
  groups.forEach(function (it) {
    var d = it[0], p = it[2];
    var g = el('g', { transform: 'translate(' + p[0] + ' ' + p[1] + ') rotate(' + p[2] + ')' }, svg);
    var aw = d.active[0], ah = d.active[1];
    if (d.status === 'offline') {
      el('rect', { x: -aw / 2, y: -ah / 2, width: aw, height: ah, fill: 'url(#' + id + 'h)', stroke: 'var(--stage-warn)', 'stroke-dasharray': '6 5', 'vector-effect': 'non-scaling-stroke' }, g);
    } else {
      el('rect', { x: -aw / 2, y: -ah / 2, width: aw, height: ah, fill: 'none', stroke: 'var(--stage-line)', 'vector-effect': 'non-scaling-stroke' }, g);
    }
    if (opts.measure === d.id) el('rect', { x: -aw / 2, y: -ah / 2, width: aw, height: ah, fill: '#0d0f13' }, g);
    if (opts.selected === d.id || opts.measure === d.id) {
      el('rect', { x: -d.body[0] / 2 - 4, y: -d.body[1] / 2 - 4, width: d.body[0] + 8, height: d.body[1] + 8, rx: 13, fill: 'none', stroke: 'var(--stage-sel)', 'stroke-width': 3, 'vector-effect': 'non-scaling-stroke' }, g);
    }
    it.push(g);
  });
  host._labels = function () {
    var sc = svg.getScreenCTM(); k = sc ? sc.a : 1;
    svg.querySelectorAll('.lbl').forEach(function (n) { n.remove(); });
    groups.forEach(function (it) {
      var d = it[0], p = it[2], g = it[3];
      var lg = el('g', { class: 'lbl', transform: 'rotate(' + (-p[2]) + ')' }, g);
      var fs = 13 / k, r = 11 / k;
      var x0 = -Math.min(d.body[0], d.body[1]) / 2 + 6 / k, y0 = -Math.min(d.body[0], d.body[1]) / 2 + 6 / k;
      if (p[2] === 90) { x0 = -d.body[1] / 2 + 8 / k; y0 = -d.body[0] / 2 + 8 / k; } else { x0 = -d.body[0] / 2 + 8 / k; y0 = -d.body[1] / 2 + 8 / k; }
      var compact = (opts.label === 'number') || k < 0.9;
      var tw = compact ? 0 : (d.name.length * fs * 0.56 + 10 / k);
      el('rect', { x: x0, y: y0, width: 2 * r + tw, height: 2 * r, rx: r, fill: '#08090c', stroke: (opts.selected === d.id || opts.measure === d.id) ? 'var(--stage-sel)' : 'var(--stage-line)', 'vector-effect': 'non-scaling-stroke' }, lg);
      var t = el('text', { x: x0 + r, y: y0 + r + fs * 0.36, 'font-size': fs, 'text-anchor': 'middle', class: 'stage-text' }, lg); t.textContent = d.n;
      if (!compact) { var t2 = el('text', { x: x0 + 2 * r + 2 / k, y: y0 + r + fs * 0.36, 'font-size': fs, class: 'stage-text' }, lg); t2.textContent = d.name; }
      if (d.status === 'offline') {
        var off = el('g', {}, lg);
        var ow = 74 / k, oh = 24 / k;
        el('rect', { x: -ow / 2, y: -oh / 2, width: ow, height: oh, rx: 4 / k, fill: '#08090c', stroke: 'var(--stage-warn)', 'vector-effect': 'non-scaling-stroke' }, off);
        el('path', { d: 'M0 -4.5 L5 4.5 L-5 4.5 Z', fill: 'var(--stage-warn)', transform: 'translate(' + (-ow / 2 + 13 / k) + ' ' + (0.5 / k) + ') scale(' + (1 / k) + ')' }, off);
        var ot = el('text', { x: -ow / 2 + 23 / k, y: fs * 0.36, 'font-size': fs, fill: 'var(--stage-warn)', 'font-weight': 700, 'font-family': 'Atkinson Hyperlegible Next, system-ui' }, off); ot.textContent = 'Offline';
      }
      if (opts.measure === d.id) {
        var A = d.active, Bo = d.body, mg = el('g', { class: 'meas' }, lg), f2 = 13 / k;
        el('line', { x1: -A[0] / 2, y1: A[1] / 2 + 14 / k, x2: A[0] / 2, y2: A[1] / 2 + 14 / k, stroke: 'var(--stage-sel)', 'stroke-width': 1.5, 'vector-effect': 'non-scaling-stroke' }, mg);
        var mt = el('text', { x: 0, y: A[1] / 2 + 10 / k, 'font-size': f2, 'text-anchor': 'middle', fill: 'var(--stage-sel)', 'font-weight': 700, 'font-family': 'Atkinson Hyperlegible Next, system-ui' }, mg); mt.textContent = A[0].toFixed(1) + ' mm';
        el('line', { x1: A[0] / 2 - 14 / k, y1: -A[1] / 2, x2: A[0] / 2 - 14 / k, y2: A[1] / 2, stroke: 'var(--stage-sel)', 'stroke-width': 1.5, 'vector-effect': 'non-scaling-stroke' }, mg);
        var mt2 = el('text', { x: A[0] / 2 - 20 / k, y: 0, 'font-size': f2, 'text-anchor': 'end', fill: 'var(--stage-sel)', 'font-weight': 700, 'font-family': 'Atkinson Hyperlegible Next, system-ui' }, mg); mt2.textContent = A[1].toFixed(1) + ' mm';
        el('rect', { x: -A[0] / 2, y: -A[1] / 2, width: A[0], height: A[1], fill: 'none', stroke: 'var(--stage-sel)', 'stroke-dasharray': '4 4', 'vector-effect': 'non-scaling-stroke' }, mg);
      }
    });
  };
  requestAnimationFrame(host._labels);
  if (window.ResizeObserver) new ResizeObserver(function () { host._labels(); }).observe(host);
  return svg;
}
function stateLinks(states) {
  var bar = document.createElement('nav'); bar.className = 'proto-bar'; bar.setAttribute('aria-label', 'Mockup states');
  states.forEach(function (s) {
    var a = document.createElement('a'); var q = new URLSearchParams(location.search); q.set('state', s[0]);
    a.href = '?' + q.toString(); a.textContent = s[1]; if (s[0] === STATE) a.setAttribute('aria-current', 'page'); bar.appendChild(a);
  });
  document.body.appendChild(bar);
}
function show(sel, on) { document.querySelectorAll(sel).forEach(function (n) { n.hidden = !on; }); }
function only(attr) { document.querySelectorAll('[data-when]').forEach(function (n) { n.hidden = n.getAttribute('data-when').split(' ').indexOf(attr) < 0; }); }
