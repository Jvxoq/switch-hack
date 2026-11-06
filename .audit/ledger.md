# audit-ai ledger

## Audits
2026-11-06 | full (plan vs proposal) | Not yet | fatal 1 · serious 6 · worth 3
2026-11-06 | recheck + full (rev 2) | Yes after rev 3 | fatal 0 · serious 3 · worth 4

## Findings
| ID | First seen | Level | Title | Status | Last checked | Evidence |
|---|---|---|---|---|---|---|
| A1 | 2026-11-06 | Fatal | Nobody owns incident state after the alert | fixed (rev 2) | 2026-11-06 | tasks.md:106, :265, :306 |
| A2 | 2026-11-06 | Serious | Detector only sees traces started since last poll | fixed (rev 2) | 2026-11-06 | tasks.md:104, :292 |
| A3 | 2026-11-06 | Serious | One action per incident blocks reopen and post-auto-pause | fixed (rev 2) | 2026-11-06 | tasks.md:219, :285 |
| A4 | 2026-11-06 | Serious | Tripwire cap only in the prompt | fixed (rev 2) | 2026-11-06 | tasks.md:312 |
| A5 | 2026-11-06 | Serious | Evals can be skipped and count as done | fixed (rev 2) | 2026-11-06 | tasks.md:330, :365 |
| A6 | 2026-11-06 | Serious | Switch unknowns on critical path, no fallback | fixed (rev 2) | 2026-11-06 | tasks.md:105, :159, :189 |
| A7 | 2026-11-06 | Serious | revert INC-n has no handler | fixed (rev 2) | 2026-11-06 | tasks.md:306 |
| A8 | 2026-11-06 | Worth | Resolved after disable_route proves nothing | fixed (rev 2) | 2026-11-06 | tasks.md:284 |
| A9 | 2026-11-06 | Worth | Loop rule misses rephrased calls | fixed (rev 2) | 2026-11-06 | tasks.md:197 |
| A10 | 2026-11-06 | Worth | Service trusts caller spend | fixed (rev 2) | 2026-11-06 | tasks.md:115 |
| B1 | 2026-11-06 | Serious | Approver came from the model | fixed (rev 3) | 2026-11-06 | tasks.md section 3 Approver identity |
| B2 | 2026-11-06 | Serious | Agent budget not reset per ask round | fixed (rev 3) | 2026-11-06 | tasks.md A01 Guard |
| B3 | 2026-11-06 | Serious | contained → verifying not a legal transition | fixed (rev 3) | 2026-11-06 | tasks.md section 3 transitions |
| B4 | 2026-11-06 | Worth | Hourly ceiling incident had no thread | fixed (rev 3) | 2026-11-06 | tasks.md E02 |
| B5 | 2026-11-06 | Worth | Concurrent writes could lose updates | fixed (rev 3) | 2026-11-06 | tasks.md section 3, S01 |
| B6 | 2026-11-06 | Worth | Headless eval vs always-ask unclear | fixed (rev 3) | 2026-11-06 | tasks.md A03 |
| B7 | 2026-11-06 | Worth | handed_off got no record | fixed (rev 3) | 2026-11-06 | tasks.md E03 |
