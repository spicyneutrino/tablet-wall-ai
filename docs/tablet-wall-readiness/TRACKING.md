# Delivery tracking

The [consolidated roadmap](ROADMAP.md) is the acceptance contract. GitHub issues
track delivery; this table links the two. An issue remains open until its
acceptance checks have evidence. A passing software test does not close a
real-tablet acceptance requirement.

[Draft PR #21](https://github.com/spicyneutrino/tablet-wall-ai/pull/21) carries
the implementation. It remains a draft while integration and acceptance are open.

| Issue | Work |
| --- | --- |
| [#7](https://github.com/spicyneutrino/tablet-wall-ai/issues/7) | Programme and integrated acceptance |
| [#8](https://github.com/spicyneutrino/tablet-wall-ai/issues/8) | Protocol 3 image capabilities |
| [#9](https://github.com/spicyneutrino/tablet-wall-ai/issues/9) | Diagnostics admission and tablet sign-in routes |
| [#10](https://github.com/spicyneutrino/tablet-wall-ai/issues/10) | Authoritative state and physical still-image controls |
| [#11](https://github.com/spicyneutrino/tablet-wall-ai/issues/11) | Whole-image fit and crop preview |
| [#12](https://github.com/spicyneutrino/tablet-wall-ai/issues/12) | Image render reports and recovery |
| [#13](https://github.com/spicyneutrino/tablet-wall-ai/issues/13) | Identity lifecycle and saved-layout repair |
| [#14](https://github.com/spicyneutrino/tablet-wall-ai/issues/14) | Atomic 2×2 and 1×4 arrangements |
| [#15](https://github.com/spicyneutrino/tablet-wall-ai/issues/15) | Calibration trust and diagnostic grid |
| [#16](https://github.com/spicyneutrino/tablet-wall-ai/issues/16) | Optional approved joining and revocation |
| [#17](https://github.com/spicyneutrino/tablet-wall-ai/issues/17) | Readiness and operations |
| [#18](https://github.com/spicyneutrino/tablet-wall-ai/issues/18) | Integrated desktop and mobile acceptance |
| [#19](https://github.com/spicyneutrino/tablet-wall-ai/issues/19) | Real-tablet acceptance evidence |
| [#20](https://github.com/spicyneutrino/tablet-wall-ai/issues/20) | Measured efficiency baseline |

Implementation uses isolated worker branches. The integration branch is
`work/tablet-wall-readiness`. Each accepted unit needs an inspected diff,
appropriate executable checks, and a decision-log entry. Interface changes also
need rendered desktop and mobile checks. Review snapshots preserve the original
assessments; their recommendations are proposals until the roadmap accepts them.

All runtime checks use temporary data and private browser sessions. The live wall
database, asset library, hotspot, and firewall are outside this implementation run.

See [DECISIONS.tsv](DECISIONS.tsv) for integration decisions, and
[QA-BASELINE.md](QA-BASELINE.md) for the initial rendered-app evidence.

## Final software acceptance

The integrated application is at `0cc4cec` for the current acceptance pass.
The full Python checkpoint is 1,782 tests; 18 Node suites pass. Actual isolated
four-tablet journeys passed 106 checks from desktop and again from phone width.
A fresh independent review passed `0529eaa`, including the 106-check journey,
delayed-response and QR races. Later generated-pattern/entry-point corrections
at `f2a8c5f` and the keyboard focus correction at `0cc4cec` have focused and
actual-browser evidence; their final acceptance mapping remains open.

The read-only acceptance audit found a real generated-pattern DTO defect at
`0529eaa`, fixed at `f2a8c5f`, and identified missing explicit acceptance
assertions. Portable feature and accessibility runners are being added for those
assertions. This is evidence completion, not a change to the accepted feature
scope. See the latest sections of [VERIFICATION.md](VERIFICATION.md).

The audit's suggestion that programme-level *software* completion needs TWR-17
is rejected. The canonical two-finish-line definition in ROADMAP §2.2 keeps
software acceptance separate from real-tablet milestone acceptance. TWR-17 and
issue #19 remain open regardless of software checks; no hardware claim follows.
Pairing remains explicitly deferred for profile A, with its residual trust risk.

Durable local evidence is under
`/var/home/oak/.local/share/tablet-wall-ai/readiness-program/`. `final-evidence/`
contains the full-suite JUnit/log, independent review report, QR probe/image,
and `run-provenance.json` with application commits and driver SHA-256 hashes.
`reviews/acceptance-audit-0529eaa.md` preserves the unedited audit. PR #21 stays
draft until final software checks and review are resolved.
