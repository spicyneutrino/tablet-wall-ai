# Unit guide for implementers

Read this whole file before you start. Follow it literally.

## What you are building

`frontend/controller-app/` is a new React + TypeScript operator console for a wall of physical tablets. It replaces the old console in `frontend/controller/` (plain JavaScript). The backend (`main.py`) must not change. Each unit adds one feature to the new app and proves it with tests against a real server.

## Where things are

- Design to match: `docs/redesign/mockups/final.html`. Open it in a browser with `?state=<name>&theme=light` or `theme=dark`. States: main, selected, arrange, measure-model, measure-size, measure-ruler, measure-review, firstrun, loading, offline, unreachable, uncertain, conflict, server, data, playback, library, components.
- Written design rules: `docs/redesign/03-visual-spec.md`.
- Plan with every unit and its Files line: `docs/redesign/04-build-plan.md` (section 2 lists every API endpoint and the old code that calls it; section 8 lists parity rows).
- UI primitives: `frontend/controller-app/src/ui/` (Button, Tabs, Field, Input, Label, ModalDialog, SideSheet, StatusBadge, Tally, ToggleGroup, DropdownMenu, Tooltip). Look at `src/dev/PrimitivesGallery.tsx` to see how each one is used. Do not write new buttons or inputs; use these.
- Tokens: `src/styles/tokens.css`. Use `var(--token)` names from it. Never write a hex colour.
- API schemas and paths: `src/api/` (zod schemas, `paths.ts` path builders). Parse every response with the schema.
- Store: `src/state/store.ts`, hooks in `src/state/hooks.ts`. Commands that write to the server go through `src/state/commands/run.ts`. Copy the pattern of an existing command and its test (`run.test.ts`).
- Shell: `src/App.tsx` and `src/features/*/index.tsx`. Each feature folder already has a stub created by the shell. Fill the stub; do not move it.
- Old code to match behaviour: the files named in your unit's brief under `frontend/controller/`. Read them to learn what the feature does. Do not copy their DOM code.
- Test harness: `e2e/fixtures.ts`. A test gets `server` (a real FastAPI server), `tablets(n)` (n real tablet pages joined), `api` (direct API calls with the right headers), `writes(page)` (records every write request the page makes), `axe(page)` (accessibility scan), `guard(page)` (fails on console errors), `tabletPixel` (reads a colour from a real tablet screen). Look at `e2e/shell.spec.ts` and `e2e/harness.spec.ts` for working examples.
- Parity test stubs: `e2e/parity/<ID>.spec.ts`. Each has one `test.fixme(...)`. Your unit's rows are named in its brief. Replace `test.fixme` with `test` and write the real test. Keep the test title exactly as it is.

## Rules

1. Only change files on your unit's Files line, plus small additive changes to `src/main.tsx`, `src/App.tsx` and `src/dev/**` to mount your work. If you need any other file, stop and say which file and why.
2. Never change files under `frontend/controller/`, `frontend/client/`, `tests/`, `main.py` or `tabletwall/`.
3. Never delete, skip or loosen a test or check to make it pass. Fix the code. If a check looks wrong, stop and report it.
4. Every interactive element needs a visible hover, focus-visible, selected (if it can be selected) and disabled state. The primitives already have these.
5. Text is 16px body. Use only the type sizes and spacing tokens in `tokens.css`.
6. No outlined "boxes". Separate areas with tone and spacing, like the mockup. Borders only on inputs, focus, selection and drop targets.
7. Every write to the server sends the `If-Match` header the plan names for that endpoint.
8. Loading, empty and error states must exist and say what to do next in plain words.

## Commands

Run from `frontend/controller-app/`:

```
npm ci
export PLAYWRIGHT_BROWSERS_PATH=$HOME/.cache/ms-playwright
BASE=$(git rev-parse HEAD)   # once, before you change anything
```

When done, run these in order and paste the real output of each:

1. `npm run typecheck`
2. `npm run lint`
3. `npm run test`
4. `npm run build && npm run build:e2e`
5. `npx playwright test <your parity spec files> --reporter=line` three times. All must pass all three times.
6. `npx playwright test --reporter=line` once (the whole suite). Report the totals. Nothing that passed before may fail now.
7. Take screenshots of your feature in the real app at 1440x900 and 390x844, light and dark, and open them. Compare with the matching `final.html` state. Fix what differs. Save them under `/tmp/<unit>-shots/` and list the paths.
8. `git clean -fdq ../controller/app ../controller/app-e2e && git checkout -- ../controller/app`
9. `git add -A . && git commit -m "<message from your brief>"`
10. `git diff --name-only $BASE...HEAD` and paste it.

Do not push. Do not open a pull request. Use a free port for any server you start yourself, never port 8012.

## Final message

Branch name, head SHA, files changed, the output of every command above, screenshot paths, and anything you could not do with the reason.
