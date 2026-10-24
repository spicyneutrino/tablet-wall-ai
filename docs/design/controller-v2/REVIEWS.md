# Controller v2: design rounds and cross-review

## Round 1

Four independent leads were asked for a plan, tokens, and a self-contained mockup. All were told to use the `anthropic-frontend-design` skill and to keep every capability.

| Lead | Provider/model | Outcome |
|---|---|---|
| Sonnet | Claude Code, `claude-sonnet-5-5` | Desktop and mobile mockups completed. Hit a Claude API rate limit before `design.md`/`notes.md`. Artifact used. |
| Opus | Claude Code / Cursor / OpenCode, `claude-opus-5-5` | One desktop mockup completed before account limits stopped every route. No mobile or docs. Artifact used. |
| Sol | Codex Work, `gpt-6.1-sol` | Complete design, desktop/mobile mockups, tiling preview, 22/22 interaction checks, notes. Used for the final synthesis mockup before a Codex limit stopped the docs. |
| Astra | Codex Personal, `gpt-6-astra` | Desktop/mobile mockups and interaction prototype completed. Hit a usage limit before docs. Artifact used. |

## Cross-review

### Native read-only review

It inspected all four desktop/mobile screenshots, read the HTML/CSS/JS, ran a DOM/responsive probe at 1440x1000 and 390x844 for all four, and ran Sol's `verify.cjs` (22/22 pass).

| Criterion | Sonnet | Opus | Sol | Astra |
|---|---:|---:|---:|---:|
| Wall state at a glance | 5 | 5 | 4 | 4 |
| Hierarchy | 4 | 5 | 4 | 4 |
| Placement interaction | 4 | 5 | 5 | 4 |
| Tiling | 5 | 4 | 5 | 4 |
| Roster and available tablets | 4 | 5 | 5 | 4 |
| Content and saved setups | 4 | 4 | 5 | 3 |
| Premium restraint | 4 | 5 | 4 | 5 |
| Capability coverage | 4 | 3 | 5 | 3 |
| Feasibility | 4 | 3 | 5 | 3 |
| Accessibility and responsive | 2 | 2 | 5 | 4 |
| Distinctiveness | 4 | 5 | 4 | 4 |
| **Total** | **44** | **46** | **51** | **42** |

Key findings:

- Sol was the only complete, verified design. Its wall was too small and its image preview clipped.
- Opus had the best desktop wall and inspector, but no viable mobile layout and a partial-tile apply.
- Sonnet had the best tiling preview and coverage warning, but its mobile `.app` scrolled 604px at 390px despite a false-negative `documentElement` check.
- Astra had the strongest palette and spatial inspector, but invented a connect action and under-specified recovery and reservation release.

### Sol cross-review of Sonnet and Astra

Sonnet won narrowly; Astra was runner-up. Sonnet's wall-first canvas and tile preview were strongest; its mobile overview was compressed and its tiling swap cells were not keyboard accessible. Astra had the best visual system and browse-then-apply content flow; its tiling shape policy and exceptional states were weaker.

## Resolution

The final design keeps:

- Sol's three-region frame, selection model, exact inspector, undo model, and mobile task approach.
- Sonnet's tiling overlay, numbered cells, click-to-swap, shape-preserving/fill choice, blocked apply, and honest request count.
- Opus's continuous single image, physical bezel treatment, Tablet/Content/Layout context rail, and exact Match screen shape copy.
- Astra's mineral palette, type hierarchy, stable roster, and image browse/apply separation (Colour and Calibration remain direct mode switches).

It rejects:

- A permanent bottom dock plus a left rail.
- A fixed mobile status bar that covers controls.
- Invented device names or a fake connect action.
- An opaque, all-or-nothing tiling claim.
- A mobile wall that is a squeezed desktop without task navigation.

## Final synthesis note

The synthesis mockups and tokens were produced by Sol before its account limit stopped the written plan. The direct Opus routes were unavailable. The final plan, design system, and implementation map were completed from the four artifacts, the two cross-reviews, and the final synthesis mockups. This is recorded so the process is not attributed to a model that could not finish.


## Calibration and numbers follow-up

Sonnet 5.5 at high effort reviewed the image-slice, display-number, and calibration plan. It approved the sign fix for the map, corrected the roster thumbnail math to a two-stage cover, recommended in-memory number allocation rather than a schema change, and required the number in the welcome (outside revision gating) so a reconnect repaints a changed number. It also recommended the number on unplaced and diagnostic screens, not just calibration. The implementation follows that memo.
