# Tablet Wall operator design

The controller chooses content, arranges screens, and reports what tablets have actually painted. Five tasks remain distinct. Image and geometry changes have separate commits.

## Visual system

| Token | Value | Use |
|---|---|---|
| `--bg` | `#EFECE4` | page canvas |
| `--surface` | `#FAF8F2` | working panels, inspector, library cards |
| `--surface-raised` | `#F3F0E8` | quiet bands, non-selected rows |
| `--text` | `#2D2822` | primary ink |
| `--muted` | `#5C564D` | secondary facts |
| `--border` | `#D8D3C7` | group and list separators |
| `--control` | `#67645D` | input and outline-control boundaries |
| `--hover` | `#F0ECE4` | hover fill |
| `--selected` | `#F5E5D7` | selected row or image wash |
| `--disabled-bg` | `#E7E1D5` | disabled controls |
| `--backdrop` | `rgb(30 26 21 / 60%)` | dialog scrim |
| `--stage` | `#22252A` | wall and image field |
| `--stage-text` | `#F2F0EA` | text on the wall field |
| `--stage-line` | `#8A8E95` | panel outlines and hatch |
| `--stage-selected` | `#FFC084` | selected panel on the wall |
| `--accent` | `#8F4014` | links, focus, selected/preview marks, hover edge |
| `--success` | `#246344` | current confirmed evidence |
| `--attention` | `#795500` | attention |
| `--error` | `#A12A24` | failure, removal |

Use Schibsted Grotesk. Body text and input values are 16px; quiet utilities and technical facts are 14px. Inline dimensions use proportional figures. Section headings are 18–20px. Keep text and controls readable at enlarged sizes.

Spacing uses 4, 8, 12, 16, 20, 24, 32 and 48px. Controls have 6px corners and at least 44px targets. Library and arrangement-tool panels have 12px corners, a quiet border, and 20px desktop or 16px phone insets. The image composer sits directly on the canvas. Avoid nested card outlines and decorative shadows.

Primary actions rest in charcoal with cream text. Rust marks links, focus, selection and hover. Utilities have an underline at rest, a thicker underline on hover-capable pointers, and no hover box. Disabled utilities have muted text and no underline. Applied configuration is neutral; it is not green display proof.

Expanded native disclosures separate nonempty content blocks by 16px. Fields align at their controls. Related actions wrap as a group. Empty messages take no visible space. Errors and warnings retain explicit feedback; routine preview-ready narration is omitted.

## Tasks

### Images

One image composer names the applied or selected image. Adjust image creates a guarded preview of the applied asset with its existing fit. The Library is the only inventory chooser. Each thumbnail button has a complete accessible filename and a selected state; applied configuration has a separate marker.

Desktop places the composer and wall in one column, with Library beside them. Portrait phone order is Library, composer, wall, source details. The horizontal phone Library exposes image choice before the large wall. Short landscape keeps the wall and Library beside each other where their effective widths permit. Narrow effective containers stack.

Fit, Show image and Discard belong to the pending image. Applied/preview comparison controls belong to the shared wall stage and work in Images and Arrange. Show is the only display commit. Rebuild appears for a stale preview. Restore previous content and the uncropped source are in Image details. Missing assets, uncertain uploads and refused commands remain explicit.

### Arrange

Local grid choices precede Preview arrangement. They do not change the wall. A rendered preview enables Apply arrangement. One Discard arrangement handles local grid inputs, server grid previews and manual edits.

Presets, membership, explicit mounting and measurement pins remain separate from the stage. The review area carries proposal facts and relevant warnings next to Apply. It does not repeat the stage's Preview state in another explanation. Keep release acknowledgement, representation-change safety copies, and stale-preview rebuilding.

### Tablets

The roster and selected-tablet inspector retain their desktop list/detail layout and phone native dialog. The actual tablet name heads the inspector. Naming stays visible. A context-specific recovery control names the real action instead of forwarding through another button.

Roster and inspector Identify invoke the same captured-target command. Roster-row DOM belongs to PhysicalStage. Placement, participation, replacement, Remove and offline Forget remain reachable. Wall issues use a native disclosure which the header Issues control opens.

### Saved

Arrangements and Scenes have distinct groups and actions. Each save form precedes its list and names the applied object it saves. Recall arrangement changes geometry; Preview scene creates a content preview. Neither group needs a repeated per-row exclusion sentence.

One Refresh reloads both inventories. Each arrangement's exact tablet identities and revision pins remain in a named Tablet details disclosure. Invalid entries and missing assets stay visible before their action. Delete and return-point recovery retain their existing guards and confirmations.

### Settings

Server checks owns server evidence and one successful-read timestamp. Live tablet display evidence stays in the header and Issues. Server-reported connection counts remain under Server and connection details. A failed check retains its last-success timestamp.

Measurements remains a named advanced entry for the selected tablet. Retained model, profile and calibration fields keep their subject, revision, conflict and ruler safeguards. Diagnostics is a native disclosure with its actual loading, error or unavailable state visible in the summary. Experimental playback retains explicit admission and its software-evidence limit. Security trust warnings and destructive confirmations remain at their decisions.

## State and code ownership

OperatorState.stageView derives the drawn layout, content, mode and editability from existing authority, geometry previews, image preview and viewLive. Workspace presentation and PhysicalStage consume that derivation. It is not a second mutable state store.

OperatorContent owns inventory, selection, fit and content commands. OperatorGrid owns grid review and application. The controller coordinates manual geometry and cross-task resolution. OperatorDevices owns tablet commands and per-subject receipts. OperatorReadiness owns server checks. OperatorSession remains the authority and write boundary.

A single stage node moves only when its task host changes. Runtime updates preserve focus. The visible stage state is Applied or Preview; a text-backed live status identifies whether the preview changes arrangement or image and whether it is applied. Viewing applied output retains the pending draft.

Draft cues belong to their task, including when another task is active. Compact navigation names inactive draft owners. The native selector keeps focus across successive arrow changes and uses the same draft-resolution flow as tabs.

## Responsive and stage contract

The header grows with its content from a 64px desktop, 56px portrait or 44px short-landscape minimum. Navigation is sticky above desktop content and fixed below portrait-phone content, including safe-area clearance. Enlarged navigation uses a native selector when its effective container cannot hold the tabs.

The stage keeps the wall aspect, geometry, gaps and bezels. Its dark field shrink-wraps the SVG and is centered when height-limited. Fitting measures available width and viewport chrome through CSS zoom and document position. A captured drag retains its starting screen matrix and field size until release. It does not use a fixed vh percentage.

Portrait Images keeps a full-width scrollable wall below the chooser. Other layouts fit available height with a usable floor and page scrolling. Pending controls remain fixed when sufficient space exists and return to normal flow when enlarged controls would obscure the wall. Inline controls wrap within their composer and shed fixed-bar backgrounds and borders.

Screen-space tablet labels target 11–13px. Small labels retain tablet numbers, or yield to the external identity list when no readable label fits. The labels are operator geometry, not tablet content. Stage technical details remain reachable from Images and Arrange.

Verify desktop, portrait, short landscape, 320px, enlarged text and CSS zoom. Inspect both viewport screenshots and component crops. Check containment against the actual parent, not just page width. Measure action reachability before automation scrolls to a button.

## Safety and verification

Choosing, uploading, fitting, viewing and discarding never apply content or geometry implicitly. Preserve ETags, generations, revision pins, read fences, serialized writes and uncertain-completion locks. Delayed work cannot replace a newer selection or move a command result to another tablet or task.

Only current matching paint tokens count as showing an image. An open socket, applied configuration, thumbnail, Identify response, server check or prepared playback is not display proof. Keep unknown, stale, hidden, offline, failed, unsupported and unavailable distinct.

Keep keyboard operation, native form controls and dialogs, focus return, reduced motion and forced-colour states. Sign-in retains inline CSP-bound styling and its system-font fallback. The compatibility guard intentionally retains its legacy palette.

Browser fixtures use disposable data and shipped clients. Emulated text enlargement and CSS zoom do not establish native mobile zoom, hardware alignment, screen-reader behavior, TLS or soak results.

## Interaction and recovery contract

Tab activation retains focus on the visible tab or compact task selector. Discard returns focus to the visible Preview control after its state update. Task navigation closes the modal tablet sheet before hiding its ancestor; measurement recovery then focuses the selected tablet model.

Fit has a persistent visible label and concise Fill/Fit values. Inline composer actions remain a grouped row and wrap within their available width. Saved validation and command receipts precede their inventory and sit beside the form. One task-level Refresh saved updates both object inventories.

Tablet placement/measurements and lifecycle controls are sibling disclosures. Exact replacement details remain nested within the deliberate replacement flow. Measurements has one visible heading at its entry. Identify in the roster, inspector and Arrange order list uses the same captured-subject command and availability predicate. Stale or missing authority disables the command; an activation-time refusal is announced with recovery guidance and makes no request.
