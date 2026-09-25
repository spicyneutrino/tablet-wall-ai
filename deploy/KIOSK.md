# Kiosk and tablet notes (Phase 3b — **pending validation**)

Guidance for keeping tablets on the wall page and their screens awake.
Nothing here has been verified on physical iPads or Android tablets yet:
every item below ends in a gate you must pass on the real device before
calling it done. Platform settings change between OS versions and
manufacturers, so check your device rather than assuming.

Companion documents: [../README.md](../README.md) (what the software does),
[README.md](README.md) (the hotspot/TLS reference),
[OPERATIONS.md](OPERATIONS.md) (service, backups).

## What the app itself does *not* do

This is the important half of the distinction: screen sleep, fullscreen and
foreground behaviour are **operating-system decisions** here, not app
features. The client page today has:

- **no Screen Wake Lock API usage** — it never asks the browser to keep the
  screen on, so the OS timer decides when the display sleeps;
- **no fullscreen request** — no Fullscreen API call, no immersive/kiosk mode,
  browser chrome stays whatever the surface provides;
- **no `visibilitychange`/focus nudge** — it does not detect being
  backgrounded, throttled or frozen and does not try to wake anything up;
- **no service worker and no offline cache** — a page loaded from cache after
  the server is gone is not a supported mode;
- **no third-party resources** — no CDN, no web fonts, no analytics; every
  script, stylesheet and image comes from the same LAN origin. (A static test
  guards this: `tests/test_deployment_guards.py` fails the build if an HTML or
  CSS file starts referencing an external host.)

Reconnection is socket-level only: the client re-registers and reconnects with
backoff after the WebSocket drops. Whether a tablet OS ever resumes a frozen
page at all is exactly the kind of thing the gates below exist to measure.

## iPad (Safari / iPadOS)

**Launch surface.** Apple documents adding the page from Safari via Share →
[Add to Home Screen](https://support.apple.com/guide/ipad/bookmark-a-website-ipadc602b75b/ipados),
with an optional ["Open as Web App"](https://support.apple.com/guide/ipad/open-as-web-app-ipad8f1f7a29/ipados)
toggle on recent iPadOS versions. Whether the toggle appears, and how a Home
Screen launch differs from a Safari tab (chrome, viewport, reload behaviour),
is version-dependent — open it both ways on your iPad and compare the
reported viewport in the controller.

**Keeping the display awake — OS setting, not an app capability.**
Apple's [Keep the iPad display on longer](https://support.apple.com/guide/ipad/keep-the-ipad-display-on-longer-ipad11dbabaf/ipados)
covers Settings → Display & Brightness → Auto-Lock; Apple notes that delaying
or preventing Auto-Lock increases power consumption, so plan for mains power
and heat on an always-on tablet. Longer Auto-Lock options are not available in
every device state, so confirm the choices your iPad actually offers.

**Locking to the page — Guided Access.** Apple's
[Lock iPad to one app](https://support.apple.com/guide/ipad/lock-ipad-to-one-app-ipada16d1374/ipados)
and [Use Guided Access on iPhone or iPad](https://support.apple.com/en-us/111795)
describe starting a session (Accessibility Shortcut, typically a triple click)
and setting a passcode. Guided Access restricts *touch* to one app; it does not
by itself stop the display sleeping, and its per-session options list is where
you look for display auto-lock behaviour on your iPadOS version. Remember you
need a documented way out (passcode/Face ID/Touch ID) or a locked tablet
becomes an unrecoverable tablet.

**Browser gate.** Everything above must be repeated with the actual page over
the actual hotspot origin: no certificate warning, image renders, WebSocket
stays up, and the page survives the Auto-Lock interval you chose.

## Android (Chrome / Android)

**Keeping the display awake — OS settings, manufacturer-dependent.**

- *Screen timeout.* Increase Settings → Display → screen timeout; the menu
  names and maximum values differ per manufacturer (Pixel's are documented in
  [Manage screen & display settings](https://support.google.com/pixelphone/answer/6111557)).
- *Stay awake while charging.* Android exposes a developer option with this
  behaviour; [Android's developer options](https://developer.android.com/studio/debug/dev-options)
  document *Stay awake: Sets your screen to stay on while the device is
  plugged in*. Unlocking developer options and the option's availability vary
  by device — check yours.
- Neither option exists in the web page. The page cannot hold the screen on.

**Locking to the page.** On an unmanaged device the documented mechanism is
[Pin & unpin screens](https://support.google.com/android/answer/9455138)
(app pinning): it confines the device to one app until unpinned, with your
PIN/pattern required to leave. Keep a known exit path.

**Kiosk-mode claims.** Treat "kiosk mode" carefully: locked-down single-app
provisioning on Android is a *device management* capability, described under
[Android Enterprise](https://www.android.com/enterprise/) (and vendor MDM
offers), not something this web page can switch on. Chrome's help does not
document a kiosk mode for consumer Android tablets, and ChromeOS/Chrome
kiosk documentation does not transfer to Android tablets — verify against your
device and browser build instead of assuming one exists.

**Launch surface.** Chrome offers "Add to Home screen" from its menu; what you
get (a shortcut or something more app-like) varies with Chrome version and
whether the site ships a web app manifest — **this client ships none**, so
expect a plain shortcut. Compare a Home Screen launch with an in-browser tab
and confirm the reported viewport.

## Certificate trust on an offline LAN

The hotspot reference uses Caddy's **local certificate authority**, and the
trial LAN has no internet. Order of operations:

1. Generate/locate the CA **before** disconnecting anything, and keep the
   **private key on the laptop only**. Tablets receive the public root
   certificate and nothing else.
2. Install that public certificate on **every** tablet while you still have a
   way to fix mistakes, then verify: the tablet URL must open with no warning
   at all. `curl -k` on the laptop proves nothing about a tablet.
   - iPadOS installs certificates as a configuration profile and *additionally*
     requires enabling full trust — Apple's
     [Trust manually installed certificate profiles](https://support.apple.com/en-us/102390)
     covers Settings → General → About → Certificate Trust Settings.
   - On Android, installation lives under the security/credentials settings
     and the exact path, and how user-installed roots are treated, differ by
     version and browser. Confirm on the device; do not assume an installed
     root is trusted.
3. Offline only *after* trust is proven. A tablet that has never seen the
   origin, or that rejects the CA with the WAN gone, has no way to recover by
   itself.

When the deployment grows up into a server with a real name, the local CA
should give way to a public certificate; that decision, and who holds the CA
key, are recorded as open in [OPERATIONS.md](OPERATIONS.md#ca-trust-decide-later).

## Network limits and offline operation

- **15–20 tablets on the laptop hotspot is the intended first trial, and it is
  unproven.** The number of clients a laptop hotspot adapter/OS sustains — with
  this traffic, TLS handshakes and image bytes — is not established by this
  project. Measure it with the real tablets; expect to discover the limit
  empirically rather than reading it off a spec sheet.
- **No CDN, no internet at runtime.** All page resources and curated images
  come from the LAN origin, so a disconnected LAN works provided Caddy, the
  backend and certificate trust were all set up beforehand. Anything that
  reaches for the internet later (font, CDN, analytics) breaks that property
  and is deliberately excluded.
- `deploy/load-smoke.py` rehearses ~20 concurrent connections through the real
  ingress, but it does not stand in for 20 physical radios, image seams, sleep
  behaviour or reconnect after a radio outage.

## Real-device gates (all required before "validated")

| Gate | iPad | Android |
| --- | --- | --- |
| Tablet URL opens with **no certificate warning** | ☐ | ☐ |
| Registration, WebSocket welcome, colour/pattern applied | ☐ | ☐ |
| Curated image renders; seam acceptable at native resolution | ☐ | ☐ |
| Page still correct after the OS display timeout / Auto-Lock interval | ☐ | ☐ |
| Survives Wi-Fi drop and reconnect (airplane mode toggle) | ☐ | ☐ |
| Home Screen launch behaves like the tab (viewport, reload) | ☐ | ☐ |
| Guided Access / app pinning entered **and exited** with a known passcode | ☐ | ☐ |
| Server restart: page recovers, roster repopulates | ☐ | ☐ |
| Hotspot holds the intended tablet count | ☐ | ☐ |

Until those boxes are ticked on hardware, the accurate status line is
*reference artifacts pending validation* — not "kiosk ready", not
"unattended".
