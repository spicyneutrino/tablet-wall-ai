# Experience acceptance supplement

The roadmap requires a separate experience verdict. `simulator/browser/experience_acceptance.py` collects evidence from shipped UI and actual shipped simulated clients. It reuses `redesign_acceptance.Rig`, its private environment, source hashing, observers, screenshots and cleanup, plus existing journey and held-response helpers. It does not modify or replace the behavioral gate.

## Run on a frozen candidate

Use the project Python environment with Playwright, Pillow and application dependencies. Choose a new artifact directory and an explicitly authorized Chromium executable. All child commands use RTK. For this machine the verified command is:

```sh
rtk proxy /var/home/oak/Codes/projects/tablet-wall-ai/.venv/bin/python simulator/browser/experience_acceptance.py \
  --artifacts /tmp/tablet-wall-experience-candidate-NEW \
  --browser /var/home/oak/.cache/ms-playwright/chromium-1200/chrome-linux64/chrome \
  --artwork /path/to/supplied.png
```

Add `--baseline` only for the historical reference. Without `--artwork`, the reused fixture generates clearly synthetic colored artwork. Supplied artwork is read locally and normalized to a private PNG; both input and served hashes are recorded. There are no uploads to an external service.

The process exit code describes capture health, unexpected console/network failures and cleanup. It is **not experience approval**. Both modes always record `experience_pass: false`; candidate output requires a human verdict. Entry findings never become product regressions solely because they occurred in baseline mode. Empty and pending-state controls can legitimately be absent or disabled. Compare populated live observations for the roadmap entry expectations.

## Evidence and interpretation

`identity.json` records source/head/branch, application file hashes, browser version, private paths, action history, shipped clients and render modes. The supplement also copies itself and records its SHA-256. Existing helpers snapshot their loaded driver sources. `experience.json` records task entry positions, visible DOM control order, focusable DOM candidates, target rectangles, first-viewport presence, center-point occlusion, art and label rectangles, and sticky/fixed controls. Each observation links viewport/full-page PNG, DOM HTML, accessibility snapshot and authoritative configuration. Request, model-response, console, network and trace artifacts remain in the same private directory.

Capture sizes are 1440×900, 390×844, 320×844 and 820×1180. The bounded journey covers empty Images/Tablets/Arrange; all five populated live tasks; an independent Identify overlay on a real shipped client; a 1×4 to 2×2 local preview; held inventory pending; and one disconnected client. Fixture construction preserves separate geometry Apply and image Show. Preview revision stability is checked without committing the preview. The simulator signature is synthetic and does not confirm physical hardware.

The entry heuristic requires some gallery/roster content and the relevant action, or shape selection and the Preview path. It does not require all advanced forms, all cards, any particular count, exact coordinates, or a canvas percentage. Disabled pending controls are recorded without being called unsafe or successful. Rectangle and center-hit checks are evidence aids. They do not establish recognizability, complete occlusion freedom, keyboard order or touch usability.

For review, compare the same fixture and viewport against the baseline. Inspect the actual screenshots and DOM order. Explain whether art, tablet identity and arrangement review now lead their tasks. Check whether labels obscure art; whether sticky actions cover fields, errors or focus at relevant scroll positions; whether entry actions are usable; and which screens remain dominated by forms. Record navigation and scroll steps if measured, without inferred time savings. This supplement does not automatically navigate every sticky or keyboard state.

Failed-image and conflict states, enlarged text, model/calibration uncertainty variants, portrait/mixed measured geometry and pointer mapping still need focused existing behavioral scenarios and manual review. The full behavior suite remains authoritative for keyed drafts, CAS, uncertainty fences, stale responses, separate previews/commits, removal/replacement review, record meanings, uploads and current render evidence. Native zoom, IME, assistive technology, physical panels, optical accuracy, sleep, ingress/TLS, video and soak are unverified here. Video remains experimental.

## Baseline observed 2026-11-02

Capture head was `d8baf80e51ed42dc11064ddfea4476bb7c01d876`. Application files match `beca736` with an empty `git diff beca736 -- frontend tabletwall deploy main.py`. Application SHA-256 is `465efeccc7fc93ce451acfbceb5136606bbe377152b4b746653c4e144e601a2a`. The executed supplement hash is `3e0dbfa27e728620a3cfaa38e4df57dd47e96a9887d8a329adc90e675686dd54`.

Private artifacts are `/tmp/tablet-wall-experience-baseline-91a83-art`. These local artifacts are not portable repository assets. `experience.json` has 44 observations and 34 observations with entry findings, including intentionally empty and pending states. Capture exited 0, without interruption, page exceptions, console warnings/errors or failed network requests. This is baseline evidence with known composition failures, not a passed experience gate.

The run used the composition work package artwork at `/var/home/oak/.local/share/tablet-wall-ai/frontend-design-concepts/2026-11-02/experience-direction-d8baf80/supplied.png`. Input SHA-256 is `42f58ea8cebdd71e1e377040f00cfce4eefc04d10e737eab8d98b6deaefb9d0c`; served PNG SHA-256 is `7c1fe10d629ac27a4fff5a32d2f16adfa935f789692d4151d79526334323151d`.

| Populated entry | 1440×900 | 390×844 | 320×844 |
| --- | --- | --- | --- |
| Active panel top | y=152 | y=768 | y=821.66 |
| Images | Library below entry; Show visible | Library below entry; Show visible | Library and Show below entry |
| Tablets | Roster and Identify below entry | Roster and Identify below entry | Roster and Identify below entry |
| Arrange | Shape visible; Preview below entry | Shape and Preview below entry | Shape and Preview below entry |

The following final-run viewport screenshots were opened and inspected directly, under the artifact directory:

- `experience-live-Images-1440x900-r2-logical-334323151d-viewport.png`.
- `experience-live-Tablets-390x844-r2-logical-334323151d-viewport.png`.
- `experience-live-Arrange-320x844-r2-logical-334323151d-viewport.png`.

The desktop image view repeats image selection and places the gallery below the first viewport. Central tablet identity/status chips cover meaningful artwork in desktop and phone stage views. The same wall diagnostics displace all phone task entries. Desktop still says “Waiting for current tablet reports” beside “4 of 4 showing.” The inspected entry screenshots do not prove action-bar occlusion freedom at every scroll/focus position. Full DOM control order and focusable candidates are retained for subsequent review. No task-time savings were measured.

## Browser availability and cleanup

Configured MCPs were inspected first. Chrome DevTools returned exactly:

```text
Could not find Google Chrome executable for channel 'stable' at:
 - /opt/google/chrome/chrome.
```

Playwright MCP returned:

```text
Error: Browser "chrome-for-testing" is not installed; expected executable at /var/home/oak/.cache/ms-playwright/chromium-1252/chrome-linux64/chrome. Run `npx @playwright/mcp install-browser chrome-for-testing` to install
```

`rtk proxy browser-harness --doctor` reported Chrome running, `daemon alive` FAIL and `active browser connections` 0. Display values were inspected and left unchanged (`DISPLAY=:0`, `WAYLAND_DISPLAY=wayland-0`, `XDG_SESSION_TYPE=wayland`). No user browser was attached.

T3 preview status initially returned `available:false`. An initial blank URL attempt returned `Preview automation open failed: Invalid preview URL (parse: https:; input length 11).` A corrected incognito blank-tab open succeeded and the owned tab was closed. The browser journey used the explicitly authorized isolated Python Playwright fallback to preserve the existing fixture lifecycle, private browser/server XDG directories and disposable DB/assets/media. Chromium reported `143.0.7499.4`.

All five contexts closed, browser disconnected, no owned browser processes remained, server process group emptied, private data was removed and its loopback port closed. The helper initially mistook the Python driver itself for Chrome because its CLI contained the executable path; the supplement excludes only its own PID from that cleanup list. No shared Caddy configuration, live DB, real tablets, hotspot or firewall was touched.

An earlier synthetic-art run in `/tmp/tablet-wall-experience-baseline-91a83` interrupted when opening Images from a pending arrangement draft correctly invoked its resolution guard. The final sequence captures pending inventory before creating that draft. `/tmp/tablet-wall-experience-baseline-91a83-v2` completed with synthetic art; the final artwork run above is the cited baseline. These are driver corrections, not product regressions.

## Cheap verification

```sh
rtk proxy /var/home/oak/Codes/projects/tablet-wall-ai/.venv/bin/python -m unittest discover -s simulator/browser -p test_experience_acceptance.py -v
rtk proxy git diff --check
```

Three tests passed. They check absent, below-fold and occluded entry targets and avoid fixture-specific count requirements. Diff whitespace checks passed. Black was unavailable (`No module named black`); no dependencies were installed. The full 38-scenario regression was deliberately not started.
