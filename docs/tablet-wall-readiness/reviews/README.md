# Review snapshots — provenance

These four files are **verbatim, unedited copies** of the independent readiness
assessments supplied for this milestone. They exist so that every roadmap
disposition can be traced to the sentence that produced it, and so that a later
reader can check whether this programme misread a recommendation.

Do not edit these files. If a report is re-issued, add the new file and update
the table below; do not replace a snapshot in place.

## Files and hashes

Copied 2026-11-01 from `/var/home/oak/.local/share/tablet-wall-ai/assessments/2026-11-01/`.
Source and copy hashes were compared after copying and matched byte for byte.
The preserved DeepSeek Markdown includes intentional trailing-space line breaks
and a final blank line. These trigger four `git diff --check` notices on the
snapshot; they are retained to preserve the original bytes. New implementation
and authored documentation are checked separately.

| Snapshot | Source file | SHA-256 | Size | Attributed to | Report date | Reviewed HEAD |
| --- | --- | --- | --- | --- | --- | --- |
| [opus-5.5-existing-report.md](opus-5.5-existing-report.md) | `opus-5.5-existing-report.md` | `e900a46595bf9ec37081ecaac2bf9bdcee693578b78db707269947cb790d519d` | 37.6 KiB | "Opus review subagent" (see mismatch note) | 2026-10-31 | `0ff56e3` |
| [sol-6.1-high.md](sol-6.1-high.md) | `sol-6.1-high.md` | `bb461c4ef25ee63ff38962931cfe8a21c5fecc13ed2499adcaa8fdf163a3e88b` | 49.2 KiB | GPT 6.1 Sol, High (Codex) | 2026-11-01 | `0ff56e30dfd6b2f92995569faa2d6e7fdc90fa8f` |
| [terra-6.1-high.md](terra-6.1-high.md) | `terra-6.1-high.md` | `5662cdc1c23491ee7b59d0294f1a218aa0bfe7a5fabcdf18f30995c9f0b1f1ff` | 20.9 KiB | GPT 6.1 Terra, High | 2026-11-01 | `0ff56e30dfd6b2f92995569faa2d6e7fdc90fa8f` |
| [deepseek-v4.1-flash.md](deepseek-v4.1-flash.md) | `deepseek-v4.1-flash.md` | `a2139caf76ee863993c9d3dfa26f582017255aa58ca950b79bb83a0d25c93318` | 53.2 KiB | DeepSeek V4.1 Flash | 2026-11-01 | `0ff56e30dfd6b2f92995569faa2d6e7fdc90fa8f` |

## Provenance mismatch: the Opus snapshot is an earlier report

The file is named `opus-5.5-existing-report.md`. Its own text says it was
"Assessed 2026-10-31 by the requested Opus review subagent" at short HEAD
`0ff56e3`. The other three reports are dated 2026-11-01 and cite the full
commit.

Three facts follow, and the roadmap treats them as facts rather than resolving
them by guesswork:

1. **It is one day older than the rest of the batch.** Its observations were
   made before the other three reviews, though at the same product commit.
2. **Its model label does not match this run's requested models.** This
   earlier assessment batch used DeepSeek V4.1 Flash, Sol 6.1 High, and Terra 6.1 High. The
   name "Opus 5.5" is not one of them, and no 5.5 Opus identifier appears in the
   document. The snapshot is therefore treated as a pre-existing assessment
   carried into the batch, not as a same-run peer.
3. **Its simulator artifacts are gone.** It records that
   `/tmp/tablet-wall-commit-review-pd29jwy_/` no longer existed when it ran, and
   its own screenshots are under `/tmp/tw-opus-assess-*`. None of those paths
   were checked for this document and none are relied on as preserved evidence.

The roadmap does not discard the report for this. Its claims were re-checked
against current source wherever a decision depends on them; the ones that could
not be re-checked are labelled `[H]` or `[U]` and never used as proof. Where its
recommendation conflicts with the other three reports, the conflict is resolved
explicitly in `ROADMAP.md` §11 and §12, not silently.

A fourth provenance detail is worth recording: the Opus report's acceptance
wording for its first recommendation says the controller should show a
"Shows images" chip. The implemented capability fix uses "Image capable". The
roadmap records the behaviour requirement, not the stale label text.

Numeric differences between snapshots are expected and are not contradictions:
the Opus snapshot reports 1,177 Python tests in 70.45 s and nine Node suites;
the programme baseline records 1,177 passed in 109.30 s; later work adds a tenth
Node suite. These are different runs at different times and under different load.
Use the command and timestamp attached to a number, never the number alone.

## What these snapshots are not

- They are not the acceptance contract. `../ROADMAP.md` is.
- They are not hardware evidence. All four reviewers either state that they did
  not touch real tablets, or separate user-reported trials from their own work.
- They are not authoritative about current behaviour after `0ff56e3`. Fixes
  have landed since; the roadmap's current-state section records them and their
  remaining acceptance.

## Handling rule for contradictions

When two snapshots disagree, the roadmap applies this order:

1. A re-checked source fact at the declared HEAD beats an unverified statement.
2. An executed test or isolated probe beats a reading of the code alone.
3. A user-reported physical observation beats a simulation, but only for the
   configuration actually observed.
4. A hypothesis never beats source, test, or hardware evidence.
5. If two proposals both survive 1–4, the one with the smaller irreversible
   change to the demonstrated wall wins, unless a hardware or security
   constraint forbids it.

The chosen resolution and its rationale are recorded in
[`../ROADMAP.md`](../ROADMAP.md) §11.9 (contradiction resolutions), §11
(disposition register), and §12 (deferred and rejected work).
