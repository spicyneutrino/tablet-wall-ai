# Tablet-wall experience roadmap

Plan prepared 2026-11-02 against `beca736ce524ba4f4ef32cb5c03743cd23081847`. Implementation, regression verification, and independent review are complete for the supervised, images-only controller. See the [current status](EXPERIENCE-STATUS.md) for evidence and limits.

The goal is a controller that feels designed for operating a tablet wall: recognizable images, connected tablets and spatial arrangements lead each task. Setup machinery and exceptional recovery controls appear when needed. This follow-up addresses composition and usability; the previous software approval remains evidence for its recorded version, not approval of this visual direction.

## Evidence and decision

The [combined diagnosis](/var/home/oak/.local/share/tablet-wall-ai/frontend-design-critiques/2026-11-02/design-diagnosis-beca736.md) reconciles the independent [Sonnet review](/var/home/oak/.local/share/tablet-wall-ai/frontend-design-critiques/2026-11-02/sonnet-5.5-high-133853-4057666/REPORT.md) and [Sol review](/var/home/oak/.local/share/tablet-wall-ai/frontend-design-critiques/2026-11-02/sol-6.1-high-cf45cb10/REPORT.md). These links identify local evidence; they are not portable repository artifacts.

Both reviews found long forms ahead of the working objects, uniform action hierarchy, diagnostic canvas treatment across tasks, weak phone task entry and conflicting status prose. Sonnet would begin with wall scale; Sol would begin with task composition. Use Sol's order: enlarging the preview alone would leave the library and roster buried. Design canvas changes alongside the task compositions, then implement them together where practical.

Keep the current font and palette provisionally. The supplied DESIGN.md is a reference, not an immutable brand requirement. Change either only when a complete visual comparison supports the choice.

## Scope and invariants

This is an images-only operator experience. Preserve these behaviors throughout:

- **Apply arrangement** changes geometry; **Show image** changes content. Keep the commands separate and explain their effects.
- Live output, arrangement preview and image preview remain distinct. Looking at live output must not discard a preview.
- Server acceptance, tablet connection and current image-render evidence remain separate facts. Acknowledgement is not proof of a lit physical panel.
- Preserve keyed drafts, field focus, conflict checks, uncertain-write reconciliation and protection against stale responses.
- Preserve physical proportions, measured/model uncertainty, pinned calibration revisions, explicit mounting decisions and offline reservations.
- Keep saved arrangements and saved scenes distinct. Retain reviewed Remove, Forget and replacement workflows.
- Keep safe upload admission and the launcher opt-in. A visual redesign must not broaden tablet or network access.
- Keep native control semantics, readable labels, keyboard operation, focus recovery and accessible touch targets.

No framework migration, backend rewrite, database migration, video work or new display modes are needed to solve the diagnosed problems.

## Ordered delivery

### 1. Select a complete composition before changing the application

Produce two structurally different desktop-and-phone concepts using the same realistic four-tablet wall and supplied artwork:

1. A large canvas with a short contextual inspector and an image-library tray.
2. Object-led task views: a gallery for Images, a roster for Tablets and a spatial editor for Arrange, with compact shared wall context.

Compare them against changing an image, identifying a tablet and reviewing a 2×2 to 1×4 change. Borrow the strongest parts into one chosen direction. Image-generation references may help explore appearance, but a small rendered prototype must establish whether the composition fits real controls and states.

Expand the chosen direction to all three tasks, Saved and Settings, with empty, pending and failure examples. Record hierarchy, spacing, typography, action roles and phone behavior in a short visual brief. Do not start another broad critique round before there is a concrete alternative to judge.

**Exit:** desktop and phone compositions identify the dominant object, primary action and deferred details for each task. No screen relies on hiding required confirmations or inventing an atomic commit. Select and record one direction before production implementation.

### 2. Establish shared status and contextual actions

Use the existing authoritative state and current-tablet predicates to derive one compact wall summary. Show connection count, current output evidence and any pending preview without repeating them in multiple neutral paragraphs. Keep failure and stale states visibly different, with text as well as color.

Replace persistent command-result prose when its waiting condition ends. For example, a successful Show followed by four current reports must no longer sit beside “Waiting for current tablet reports.” Put technical provenance and extended explanations behind labelled details, while keeping actionable approximation warnings visible.

Show Rebuild, conflict resolution and other recovery actions only in states that need them. Preserve a clear path to discard an actual draft. Do not fill a healthy Images view with large disabled recovery buttons.

**Exit:** pending, applied, showing, stale, offline and failed examples are internally consistent. Delayed reports cannot clear a newer preview or imply that a failed request succeeded.

### 3. Rebuild daily tasks as complete vertical slices

Implement markup, styles and presentation events together for each slice, in this order:

| Task | New composition | Exit condition |
| --- | --- | --- |
| Images | Lead with recognizable library thumbnails. Keep selected art, Fit/Fill and Show together. Put Add image and search in the library toolbar. Remove redundant selection surfaces where an accessible replacement exists. | An operator can find, preview and show an image from this task without scrolling through setup or recovery machinery. Uploading adds to the library without silently showing it. |
| Tablets | Lead with the roster on a populated wall. Keep selection, Identify, name and placement actions close to the chosen tablet. Add tablets opens joining help; an empty roster leads with joining help automatically. | Identify and ordinary tablet inspection are available at entry. Adding, taking off the wall, forgetting and replacing remain distinguishable and retain their review guards. |
| Arrange | Lead with shape, chosen tablets and the resulting spatial preview. Keep the review summary and Apply near that result. Expand per-tablet model, mounting and calibration details when needed. | A 2×2 or 1×4 preview does not require traversing repeated advanced forms. Required hardware decisions remain explicit, and custom editing still works. |
| Saved / Settings | Make saved arrangements and scenes easy to scan. Lead Settings with readiness and useful checks; place Clear wall and other destructive actions in a labelled lower-priority area. | Routine recall and readiness do not compete with destructive controls. Existing record meanings remain unchanged. |

Phone composition is part of each slice, not a later CSS pass. Keep first-run guidance for first-run conditions; do not keep “build your first wall” guidance prominent after a wall is operating.

### 4. Give the canvas a purpose in each task

Separate visual presentation from the existing live/preview state:

- **Images:** emphasize the audience artwork. Move identity labels away from its center; offer diagnostic details on demand.
- **Arrange:** show boundaries, gaps, bezels, dimensions, overlap and preview distinctions where they help editing.
- **Tablets:** emphasize selection, identity and device health, with artwork as context.

Fit the drawing viewport to the actual arrangement and available space rather than using one fixed 3:2 frame for everything. Test a wide 1×4, a 2×2, portrait tablets and mixed measured sizes. Preserve real gaps and physical aspect. Do not change the scene's Fit/Fill behavior or stretch tablets to occupy more pixels.

On phones, put the active task and useful action near the top. Use compact, expandable wall context; give spatial editing enough room when opened. Keep action bars visible without covering fields, errors or keyboard focus. A large desktop diagram and a miniature phone copy need not share the same reading order.

**Exit:** the picture can be judged without central diagnostic chips, geometry can still be edited accurately, and every visible identity/status has an accessible equivalent. Pointer-coordinate mapping and keyboard selection remain correct after viewport changes.

### 5. Finish the visual language after the structure works

Give primary commits, secondary editing actions, quiet utilities and exceptional recovery actions distinct roles. Use typography and spacing to separate task title, selected object, state and help. Reduce repeated containers and prose rather than simply reducing font size or padding.

Use a small set of deliberate compositions backed by shared tokens and native controls. Keep status color semantic. Use animation only for a useful transition or state change, with reduced-motion support. Avoid decorative hardware silhouettes unless they communicate real model or mounting information.

**Exit:** paired screenshots show a coherent product across tasks without making every section look like the same outlined form. Readability, contrast, focus and touch targets survive the polish.

### 6. Require functional and experience acceptance

Run an independent review against a frozen candidate. Use actual shipped simulated clients and supplied artwork on isolated data, not only static mockups.

**Experience gate:**

- At 1440×900 and 390×844, Images exposes recognizable library content and its relevant Show action; Tablets exposes roster content and Identify; Arrange exposes shape selection and a useful preview/review path without traversing advanced details.
- Check 320px reflow, a tablet viewport and enlarged text separately. On phone, the active task must not be displaced by the same full diagnostic block on every tab.
- Capture all tasks plus empty, live, preview, offline, failed-image and conflict states. Inspect screenshots, console/network failures, focus movement and action-bar occlusion.
- Compare entry positions and navigation/scroll steps against the baseline for the same fixture. Report observations rather than inventing task-time savings.
- A reviewer must explain what makes the interface specific to operating a tablet wall and identify any remaining form-dominant screen. Automated overflow and contrast checks alone cannot pass this gate.

**Functional gate:**

- Adapt the existing browser acceptance scenarios to the new presentation while preserving their behavioral assertions.
- Verify previews and separate commits, uncertain writes, stale responses, draft ownership, removal/replacement, saved recall, upload isolation and current render evidence.
- Run focused tests after each slice, then the full appropriate Python/Node suites and static checks on the integrated candidate. Fix new findings before approval.

Both gates must pass. Existing native zoom, IME, screen-reader/assistive-technology, real tablet, optical, sleep, TLS and soak gaps remain explicit until separately exercised.

## Ownership and tracking

Use one implementation owner for each slice's markup, CSS and presentation events. Name a sole writer for shared files such as `physical.js`; independent reviewers and visual testers work read-only or own separate test files. Use isolated worktrees for parallel implementation. This avoids repeating the earlier CSS-only handoff after structure had already been fixed.

Track six ordered work packages corresponding to the phases above. Each closes with a short result, before/after captures, source identity, verification and remaining limits. Do not create separate feature tickets for every cosmetic observation. A package is ready for implementation only when its intended composition and observable exit condition are clear.

The existing [architecture](ARCHITECTURE.md) and [acceptance](ACCEPTANCE.md) remain the behavioral baseline. Amend their contracts only where the selected composition requires a real change; do not rewrite historical approval records. Once implementation starts, record discovered requirements or scope changes rather than silently expanding this roadmap.

## First implementation priorities

After composition selection: shared status truth and contextual actions; Images as the first complete desktop/phone slice; then Tablets and Arrange. Canvas improvements accompany those slices. This order should produce an early, assessable improvement to a daily task instead of another broad reskin.

Completion means the integrated controller passes both gates and the results are documented. It does not imply a merge, deployment, unattended readiness or hardware acceptance.
