# Kiosk check: browser APIs and OS settings

Status: the browser probe is a software check. Guided Access, Auto-Lock,
screen pinning, managed-kiosk policy, power and thermal behaviour are operator
evidence on a physical tablet. Neither half closes the `kiosk` gate by itself,
and every record keeps `hardware_gate_status = MISSING` until the operator
signs a physical acceptance record.

The client does not render a separate wake-lock chip. It requests a screen
wake lock where the browser allows one, reports `held`, `released`,
`unsupported`, `insecure` or `denied` in its heartbeat, and the controller
roster stores that value. Read the reported state from `/devices`; do not
invent a DOM chip.

## What the browser can prove

The production page is `/client/`. These checks are read-only. Do not edit the
client, add query flags, or enable a debug mode for them.

| Check | Browser source | What it proves | What it cannot prove |
| --- | --- | --- | --- |
| Secure context | `window.isSecureContext` | The page is on HTTPS or a trusted localhost origin | The tablet trusts the installed CA without a warning |
| Wake-lock API | `navigator.wakeLock` | The API exists in this browser and context | The OS will keep the display on, or that the lock survives lock/unlock |
| Wake-lock state | Heartbeat `wake_lock` in `/devices` | The last state the page reported | The physical screen stayed lit |
| Fullscreen control | `#fs-toggle` hidden/display/`data-visible` | The button exists and is offered when the API exists | A user gesture, OS kiosk policy or app-switcher lock |
| Viewport and DPR | `innerWidth`, `innerHeight`, `devicePixelRatio` | What CSS pixels the page sees | Physical panel size, bezel or calibration |
| Display mode | `matchMedia('(display-mode: standalone)')`, `document.fullscreenElement` | Tab, installed web app or fullscreen at the moment of the probe | That the mode survives a reload or an OS restart |
| Visibility | `document.visibilityState` and `visibilitychange` | The page saw foreground/background transitions | That the OS did not freeze or throttle the page |
| Page lifecycle | `pagehide`, `pageshow`, `freeze`, `resume` | Which lifecycle events this browser emitted | A guaranteed resume, or a memory kill that emitted nothing |

The browser probe is `desktop-browser` evidence. A probe on a physical tablet
is still not a substitute for the OS checks below. A browser cannot report
whether Guided Access is enabled, whether Auto-Lock is set to Never, or
whether a managed-kiosk policy is installed.

## Probe procedure

Use this on desktop Chromium first, then repeat on the real tablet browser.
The page must be the installed origin over the real hotspot, not a loopback
copy, for the tablet record.

1. Open the origin's `/client/` page and wait for the status pill to reach
   `connected`.
2. Within five seconds of load, note whether `#fs-toggle` is visible. The
   client shows it for five seconds, then hides it until the next touch. A
   browser without the Fullscreen API never shows it.
3. Open the browser developer tools or remote inspector. On iPadOS use Safari
   Web Inspector on a Mac. On Android Chrome use `chrome://inspect` from a
   development host. Do not paste the probe into a page other than the wall
   client.
4. Paste the probe below and run it once. Save the returned JSON as
   `kiosk-browser-check.json` outside the repository.
5. Read the roster value separately. The probe prints `roster.wake_lock` for
   the current device identity. It does not request or release the lock.
6. Background the browser for at least ten seconds, return to the page, and
   run the lifecycle read. Record every event with its timestamp.

```js
(async () => {
  const eventsKey = 'tw-kiosk-check-events';
  if (!window.__kioskCheckInstalled) {
    window.__kioskCheckInstalled = true;
    const previous = JSON.parse(localStorage.getItem(eventsKey) || '[]');
    localStorage.setItem(eventsKey, JSON.stringify(previous.slice(-49)));
    ['visibilitychange', 'pagehide', 'pageshow', 'freeze', 'resume'].forEach((type) => {
      document.addEventListener(type, () => {
        const rows = JSON.parse(localStorage.getItem(eventsKey) || '[]');
        rows.push({type, at: new Date().toISOString(),
                   visibility: document.visibilityState});
        localStorage.setItem(eventsKey, JSON.stringify(rows.slice(-50)));
      });
    });
  }
  const toggle = document.querySelector('#fs-toggle');
  const toggleStyle = toggle ? getComputedStyle(toggle) : null;
  const fullscreenControl = toggle ? {
    hidden_attribute: toggle.hidden,
    display: toggleStyle.display,
    visibility: toggleStyle.visibility,
    data_visible: toggle.getAttribute('data-visible'),
    label: toggle.getAttribute('aria-label'),
    supported: typeof document.documentElement.requestFullscreen === 'function',
  } : null;
  await new Promise((resolve) => setTimeout(resolve, 6000));
  const deviceId = localStorage.getItem('tablet-wall-device-id');
  let roster = null;
  try {
    const response = await fetch('/devices', {cache: 'no-store'});
    const rows = await response.json();
    roster = deviceId && rows[deviceId] ? {
      online: rows[deviceId].online,
      wake_lock: rows[deviceId].wake_lock,
      number: rows[deviceId].number,
    } : null;
  } catch (error) {
    roster = {error: String(error)};
  }
  const result = {
    checked_at: new Date().toISOString(),
    url: location.href,
    secure_context: window.isSecureContext,
    wake_lock_api: !!navigator.wakeLock,
    reported_wake_lock: roster && roster.wake_lock,
    roster,
    status: document.querySelector('#status')?.dataset.state || null,
    viewport: {
      width: window.innerWidth, height: window.innerHeight,
      dpr: window.devicePixelRatio,
      visual_viewport: window.visualViewport ? {
        width: visualViewport.width, height: visualViewport.height,
        scale: visualViewport.scale,
      } : null,
    },
    screen: {
      width: screen.width, height: screen.height,
      orientation: screen.orientation ? {
        type: screen.orientation.type, angle: screen.orientation.angle,
      } : null,
    },
    display_mode: {
      standalone: matchMedia('(display-mode: standalone)').matches,
      fullscreen: !!document.fullscreenElement,
    },
    fullscreen_control: fullscreenControl,
    visibility: document.visibilityState,
    lifecycle_events: JSON.parse(localStorage.getItem(eventsKey) || '[]'),
  };
  console.log(JSON.stringify(result, null, 2));
  const blob = new Blob([JSON.stringify(result, null, 2)], {type: 'application/json'});
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = 'kiosk-browser-check.json';
  link.click();
  return result;
})()
```

Pass conditions for the browser half:

- `secure_context` is `true` on the real origin.
- `reported_wake_lock` is `held` for an HTTPS page that is visible and has had
  at least one heartbeat interval to report the state. The probe waits six
  seconds before reading the roster. `insecure` is expected on plain HTTP and
  is a failure for the installed kiosk. A desktop headless browser can report
  `released` or `denied` even when the API exists. Record that as a browser
  limitation and repeat on the tablet.
- `fullscreen_control.supported` and `fullscreen_control.hidden_attribute`
  agree with the browser. Chromium usually offers the control. iPhone Safari
  usually does not. A hidden button after five seconds is normal.
- `viewport.width` and `viewport.height` match the orientation and the
  calibration record within the operator's declared tolerance.
- `visibility` is `visible` while the probe runs.
- The lifecycle list shows the background and return. A missing event after a
  long background period is an unobserved interval, not a pass.

## Per-platform operator steps

### iPadOS Safari and Home Screen web app

1. Record the exact iPad model, iPadOS version, Safari or Home Screen launch,
   and the display settings.
2. Set Settings > Display & Brightness > Auto-Lock to the longest interval the
   device offers for the test, or Never where the OS allows it. Apple documents
   that a longer interval increases power use and heat. Use mains power.
3. Open the page over the real installed origin and confirm there is no
   certificate warning, the page renders, the status reaches `connected`, and
   the WebSocket survives a five-minute idle period.
4. Run the browser probe. Record the reported wake-lock state and the button
   visibility. Tap once and confirm the Full screen button returns for five
   seconds. Press it and confirm the browser enters fullscreen. Exit and
   confirm the page still paints.
5. Enable Guided Access from Accessibility > Guided Access. Set a passcode and
   write down the exit method. Start a session with the wall app in front.
   Confirm that the Home gesture and app switcher are restricted. Confirm
   whether Auto-Lock still fires inside the session on this iPadOS version.
   Guided Access restricts touch to one app. It is not a display-sleep setting.
6. Lock and unlock the iPad. Record how long the page takes to become visible
   and whether the wake lock is reacquired. The page reports the state; the
   physical screen is the operator's observation.
7. Remove Guided Access only after recording the passcode and exit procedure.

### Android Chrome and managed kiosk

1. Record the exact manufacturer, model, Android version, Chrome version and
   launcher.
2. Set Settings > Display > Screen timeout to the longest value allowed, or
   Never where available. Disable adaptive battery restrictions for Chrome
   only when the operator policy allows it, and record the change.
3. Open the origin in Chrome and confirm no certificate warning, a connected
   status, the page renders, and a five-minute idle period keeps the socket.
4. Run the browser probe. Tap once and test the Full screen control as on
   iPadOS. Chrome may differ in whether the button is offered in a Home Screen
   web app.
5. Enable screen pinning or the managed-kiosk policy that the device fleet
   uses. Confirm the Home and Recents gestures are restricted and that the
   documented exit method works. A managed kiosk may suppress the fullscreen
   button; record that as a policy observation, not a client defect.
6. Lock and unlock the device. Record the page's reported wake-lock state and
   whether the screen stays lit. Repeat with the charger connected and
   disconnected if the fleet uses both.
7. For a managed fleet, record the policy identifier and the management
   console's device state. Do not assume a consumer Settings screen is the
   whole policy.

### Desktop Chromium reference

Run the same browser probe on the operator workstation against the same
origin. It validates the client's browser API path only. It cannot stand in
for iPadOS, Android or any physical display, and it never closes the gate.

## OS evidence and the gate

The OS half is evidence the browser cannot produce. Record all of these in the
operator worksheet:

| Item | Example record | Failure consequence |
| --- | --- | --- |
| Auto-Lock or screen timeout | `Never`, or `15 min` with the exact menu path | Screen sleeps during the soak |
| Guided Access or pinning | enabled, passcode stored offline, exit tested | Unattended device leaves the wall or cannot be recovered |
| Managed kiosk | policy id, console state, update channel | Policy update returns the device to the launcher |
| Power and heat | charger model, ambient temperature, device temperature | Thermal shutdown or battery damage |
| Orientation lock | portrait or landscape, matching calibration | Wall clipped or rotated |
| Browser update state | version and update channel | Silent update changes fullscreen or wake-lock behaviour |
| Exit and recovery | documented steps, tested on the device | A locked tablet becomes unrecoverable |

The kiosk gate stays `MISSING` until the operator supplies a dated record that
names the device, OS, browser, origin, browser-probe file, OS settings,
physical observations and the person who signed it. A green browser probe is
not a kiosk acceptance.

## Boundaries

- Do not change the production client to make a probe pass.
- Never enable a debug flag, bypass a certificate warning, or use `-k` as
  evidence of installed trust.
- Do not treat a desktop Chromium result as a tablet or iOS result.
- Do not treat the browser wake-lock state as a guarantee that the display
  stays on. Apple and Android both document OS-level display controls that
  the page cannot override.
- A page that is frozen by the OS may emit no `pagehide` or `freeze` event.
  Record the unexplained gap instead of claiming a clean lifecycle.
