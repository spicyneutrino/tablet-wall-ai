# Delivery tracking

The [consolidated roadmap](ROADMAP.md) is the acceptance contract. GitHub issues
track delivery; this table links the two. An issue remains open until its
acceptance checks have evidence. A passing software test does not close a
real-tablet acceptance requirement.

[PR #21](https://github.com/spicyneutrino/tablet-wall-ai/pull/21) carries
the implementation. Software acceptance passed; hardware acceptance remains open.
The branch has not been merged to main.

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

The final independent review **passed frozen `29148ec`**. TWR-01 through
TWR-14 and TWR-16 are Software complete under ROADMAP §2.2. TWR-15 is explicitly
deferred for trusted profile A. TWR-17 and programme issue #7 remain open for
real-tablet acceptance. Software delivery issues close on their own recorded
acceptance; those closures do not mean the branch is merged or hardware passed.

The full Python checkpoint passed 1,782 tests. All 18 Node suites, production
Ruff and mypy for 47 files pass. The fresh independent feature run passed
183 checks, zero failures and zero findings, plus 192 focused Python tests.
Prior desktop-led and phone-led journeys each passed 106 checks. Strict
accessibility acceptance passed 82/82; its independent review also passed
23 supplemental browser edge cases. Original failures and their corrections
remain in the records.

See [final independent review](reviews/FINAL-SOFTWARE-REVIEW.md),
[feature acceptance](FEATURE-ACCEPTANCE.md),
[accessibility acceptance](ACCESSIBILITY-ACCEPTANCE.md), and
[VERIFICATION.md](VERIFICATION.md) for commands, source identities and limits.
The efficiency baseline remains pinned to `8c3356a`; no optimisation was applied.
The restart feature runner's network filter is broad, so it is not the clean
network gate. The earlier clean browser and strict accessibility runs provide
that separate evidence.

Durable local evidence is under
`/var/home/oak/.local/share/tablet-wall-ai/readiness-program/`. The frozen final
review is copied to `final-evidence/independent-29148ec/`. The original audit
is retained in `reviews/acceptance-audit-0529eaa.md` there. Its proposed hardware
prerequisite for *software* completion is rejected under ROADMAP §2.2.

The overall milestone remains open. Follow [HARDWARE-ACCEPTANCE.md](HARDWARE-ACCEPTANCE.md)
for measured 2×2/1×4, seams, rotation, OS sleep/Wi-Fi recovery, host restart and
powered-soak evidence. No new measurement request is a prerequisite to that
trial. Pairing is not implemented; shared/untrusted-network use is unsupported.
Video remains experimental. The live wall, hotspot, firewall and service were
untouched.
