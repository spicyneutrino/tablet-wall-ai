# Controller redesign: shared brief

## The user's goal
The owner runs a wall of physical tablets (Pixel C, 2014–2015 iPads and iPad minis) from an operator console ("controller") in a laptop browser. The console works but is hard to use: long scrolling sections, too many controls on screen at once, unclear next step, weak visual hierarchy. They want the controller redesigned from scratch in a modern stack, with design, UI and UX first, while every current feature keeps working against the existing backend unchanged.

## Repository
- Repo: /var/home/oak/Codes/projects/tablet-wall-ai (branch `redesign/direction-b`, clean). Do not commit. Do not edit `frontend/` or backend code in this phase.
- Controller today: `frontend/controller/physical.html` plus classic scripts (`physical.js`, `operator-*.js`, `physical-stage.js`) and CSS (`operator-workspace.css`, etc.).
- Tablet client: `frontend/client/` stays plain HTML/CSS/JS. It is out of scope except that nothing may change its contract.
- Backend: FastAPI `main.py` (REST under `/api/...`, WebSockets `/ws/...`, ETag If-Match on wall writes).
- Prior research, read before inspecting code:
  - `docs/frontend-migration/PROPOSAL.md` (migration plan, arrangements, owner decisions).
  - `docs/frontend-migration/audit/` four audit reports (controller inventory, client, backend interfaces, tests). Use them as the feature and contract inventory instead of re-deriving it.

## Target stack (controller only)
React + TypeScript + Vite + Tailwind CSS + shadcn/ui + Lucide icons. Operators use current Chrome and Safari on a laptop, so modern CSS and Tailwind v4 are fine for the controller. Built files will be committed so `make run` needs no npm.

## Running the app
- A server is already running: http://127.0.0.1:8012/controller/physical.html (data in the scratchpad `inspect.db`). Do not stop it.
- Its four placed tablets are offline until clients connect. To bring them online, open headless pages at `http://127.0.0.1:8012/client/` in separate browser contexts with this init script per id: `localStorage.setItem('tablet-wall-device-id', ID)`. IDs: 1eb61a6f-0872-4cb4-9107-6523136723ae, 4e7c531d-d258-45a5-b787-e4e8ccc5a1c9, 77102722-0801-455f-bce3-a14617ef096a, 9c6eb4a2-2f52-4452-92c4-465c5d32c227. A working Playwright example is `scratchpad/tour.py` (run with `PLAYWRIGHT_BROWSERS_PATH=$HOME/.cache/ms-playwright uv run --group browser python ...`).
- If you need to mutate state freely, start your own server on another port with a copy of the DB: `TABLET_WALL_DB=<copy> uv run fastapi run main.py --host 127.0.0.1 --port <8013|8014>` and stop it when done.
- Browser work: per ~/AGENTS.md, use `agent-browser` (run `agent-browser skills get core --full` first) with a named session, or Playwright. Close sessions when finished.

## Skills to load (use the Skill tool, read them, apply them)
- `impeccable` (critique, audit, layout, typeset, colorize, polish), `frontend-design`, `web-design-guidelines`, `ui-ux-pro-max`, `prototype`, `modern-web-guidance`, `unslop` for prose.

## Measurable design rules (apply, do not just eyeball)
| Property | Rule |
|---|---|
| Typography | One defined scale for title, heading, body, label, caption |
| Body size | 16px base |
| Hierarchy | Size + weight + spacing + placement, not colour alone |
| Body contrast | ≥ 4.5:1 (WCAG 2.2 AA) |
| Large text contrast | ≥ 3:1 |
| Interactive states | Visible hover, focus-visible, selected, disabled |
| Spacing | One token scale, no arbitrary margins |
Verify contrast and a11y with axe-core in a real browser (e.g. inject axe from cdnjs or `npx @axe-core/cli`), not by assertion.

## Writing
Plain, short sentences. No filler or hype. Cite file:line for claims about code. Mark anything inferred or guessed as such.

## Decision (owner, after reviewing docs/redesign/01-critique.md and 02-directions.md)
- Chosen: Direction C (Preview + On wall), plus A's on-canvas layout editing and B's "Next step" card. Mockup: docs/redesign/mockups/c.html (sources in mockups/src/).
- Owner's visual feedback on the mockups: "looks a bit without polish ... lots of UI elements with outline adds a boxed feel, all UI elements have a border and are just put together. Doesn't give a fluent visual experience." So: separate regions with surface tone, spacing and elevation instead of outlines; borders only where they carry meaning (inputs, focus, selection, drop targets); fewer nested containers; buttons with filled/ghost hierarchy rather than outlined boxes; a calm, continuous surface. Contrast rules still apply (UI component boundaries ≥ 3:1 where a boundary is the only cue).
- Defaults chosen for the open questions (the owner may override):
  1. During a conflict the "On wall" view shows what the wall actually shows now (server truth); the incoming change appears in the conflict review.
  2. Preview is marked with the primary action colour, not green; green stays reserved for healthy status.
  3. Phone: one "On wall" line under the preview that expands to the small live view on tap.
