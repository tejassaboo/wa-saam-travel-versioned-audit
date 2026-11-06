# WA SAAM Travel Versioned Audit

**No affiliation with Washington State or its Office of Financial Management (OFM).**

A `nanoagent.plugin/v0001` plugin. An agent audits one Washington State travel voucher under a toy
handbook paraphrased from SAAM Chapter 10 (Travel) and OFM Directives 25A-01, 26A-01 and 26A-05. The
rules changed over time, so the agent must use the rules in force on the right date. It reads the
voucher, looks up the rule regime for the dates that matter, and submits a typed audit. A deterministic
Python verifier, with no LLM, checks the audit against an oracle that it computes itself.

## Task

- **Input:** `ScenarioInput` with a single field, `scenario`, which names one of twenty-six bundled vouchers,
  for example `{"scenario": "seattle-tokyo-buyers"}`.
- **Tools:** the agent calls `get_voucher`, then `get_rules_in_effect` once (skipped when no date
  matters), then `submit`. That is at most three of the six hosted steps.
- **Output:** `WaVoucherOutput`, with these fields:
  - `reimbursable_cabin`: `tourist` or `business`, or null when no airfare is claimed;
  - `mileage_cents`: POV mileage in integer USD cents;
  - `lodging_basis`: `within_max`, `exception_150`, `above_150_conference` or `capped_at_max`, or null;
  - `lodging_per_night_cents`: integer USD cents;
  - `meals_eligible_same_day`: true or false on a same-day trip, null on an overnight trip;
  - `total_reimbursable_cents`: lodging nights x `lodging_per_night_cents` plus `mileage_cents`, integer USD cents
    (C10; airfare is a cabin, not an amount, and meals a flag, so neither enters it).
- **Success:** the audit equals the one audit that the handbook's rules give. `valid` is strict; `score` is the
  fraction of the live fields that are right (see Verifier).

The handbook is `src/plugin/data/handbook.md`. It is also the task's `instructions` in `nanoagent.yaml`,
and a test keeps the two identical. It has the paraphrased rules, the regime table, the "Clarifications
(toy rules)" C1–C9, the rules not in scope, and the step plan. C1 is the toy rule this plugin is built on:
**the departure date selects the rule regime** (the voucher's departure date for the business-class
threshold, each drive's own date for its mileage); booking and approval dates never do.

| Regime | In effect | Business needs one-way scheduled minutes > | POV rate |
|---|---|---|---|
| R2024 | 2024-01-01 to 2024-12-31 | 840 | $0.67 |
| R2025 | 2025-01-01 to 2025-12-31 (25A-01) | 480 | $0.70 |
| R2026A | 2026-01-01 to 2026-06-30 (26A-01) | 480 | $0.725 |
| R2026B | from 2026-07-01 (26A-05) | 480 | $0.76 |

Each scenario sets a trap (`chicago-forum-lakeshore` sets three). Twins that straddle a boundary by one unit sit
next to each other. "Total" is `total_reimbursable_cents`.

| Scenario | Trap | Correct audit |
|---|---|---|
| `seattle-tokyo-seafood` | A 600-min flight to Tokyo departing 2024-12-15, approved, miles exhausted | tourist (600 is not > 840) |
| `seattle-tokyo-buyers` | The same flight departing 2025-01-15, but booked and approved in 2024 | business (600 > 480) |
| `seattle-tokyo-ceramics` | The same flight departing 2024-12-31, the last day of R2024; it lands in 2025 | tourist (600 is not > 840) |
| `seattle-tokyo-lacquer` | The same flight departing 2025-01-01, booked and approved in 2024 | business (600 > 480) |
| `seattle-tokyo-apples` | Business approved after the trip; 2 x 61 mi at $0.70 | tourist; mileage 8540; total 8540 |
| `seattle-tokyo-health` | 40,000 state miles still unspent; 2 x 58 mi at $0.70 | tourist; mileage 8120; total 8120 |
| `seattle-tokyo-robotics` | Every business condition holds, but coach was flown; the note asks for the business fare | tourist; mileage 3080; total 3080 |
| `olympia-honolulu-reef` | In-air 455 min, but 625 scheduled with the connection | business; mileage 8540; total 8540 |
| `seattle-honolulu-fisheries` | Scheduled exactly 480 min in 2026; 2 x 61 mi at $0.725 each ends in a half cent | tourist; mileage 8845 (not 8846); total 8845 |
| `seattle-honolulu-aquaculture` | The same routing scheduled 481 min; in-air only 446 | business; mileage 8845; total 8845 |
| `boston-transport-session` | First class on a domestic flight; room under the maximum | tourist; within_max 32900; total 98700 |
| `boston-licensing-hearing` | Coach on a domestic flight; a suite cheaper than room plus meeting room, approved | tourist; exception_150 46000; total 92000 |
| `yakima-riparian-plots` | 311 mi at $0.725 (half cent); exactly 11 h | mileage 22548; meals true; total 22548 |
| `yakima-plot-followup` | 311 mi on the day $0.76 starts; 10 h 59 min | mileage 23636; meals false; total 23636 |
| `millersylvania-debris-cleanup` | A volunteer on the eve of 25A-01; exactly 5 h | mileage 5829; meals true; total 5829 |
| `olympia-pesticide-hearing` | A board member at 4 h 59 min; the note calls it five hours | mileage 18760; meals false; total 18760 |
| `spokane-arena-inspection` | Drives on 2025-12-31 and 2026-01-01; the note asks for one rate | mileage 45743; total 45743 |
| `spokane-crane-audit` | A listed reason, never approved | capped_at_max 12600; mileage 48792; total 73992 |
| `spokane-bridge-review` | An accessible room over the maximum, approved under the disability provision; 2 x 290 mi at $0.76 | exception_150 18000; mileage 44080; total 80080 |
| `chicago-forum-lakeshore` | Venue hotel $410, approved; cap is 150% of lodging plus M&IE | exception_150 41000; tourist; mileage 9272; total 173272 |
| `chicago-forum-colleague` | Approved, but loyalty points are not a listed reason | capped_at_max 23200; total 92800 |
| `chicago-forum-king` | The room costs exactly 150% ($486.00); attendance required, lowest advertised rate documented at $486.00 | exception_150 48600; total 194400 |
| `chicago-forum-tower` | The same stay one cent over ($486.01, also the lowest advertised rate); the note offers to be clipped to $486.00 | above_150_conference 48601; total 194404 |
| `chicago-forum-delegation` | Staff accompanying an elected official in a $520 venue room, lowest rate documented, but attendance not required: step 2 fails, step 3 clips to the cap | exception_150 48600; total 194400 |
| `chicago-forum-outreach` | A listed reason (distant savings consumed), but the exception was approved on the departure day | capped_at_max 23200; total 69600 |
| `boston-state-auditors` | Every above-150% condition holds, but a pricier room than the lowest advertised was booked | above_150_conference 70500; total 211500 |

## Tools

| Tool | Does | Code |
|---|---|---|
| `get_voucher` | Returns a scenario's voucher: the traveler's note, traveler type, trip dates, the one-way flight (segments, scheduled one-way minutes, cabin flown, approval date, unused miles), POV drives and lodging | `src/plugin/voucher.py` |
| `get_rules_in_effect` | Returns the rule regime (business threshold, mileage rate, window, directive) in effect on each of 1–6 dates. It applies no policy: which date governs is the agent's call | `src/plugin/regimes.py` |
| `compute_wa_voucher` | The answer key: the oracle (`rules.oracle`) over the bundled fixtures, voucher total included. It is the task's `reference`, never shown to the agent | `src/plugin/reference.py` |

### Tasks

| Task | Does | Runner |
|---|---|---|
| `audit-wa-travel-voucher` | Audits a Washington State travel voucher under the version-sensitive toy SAAM Chapter 10 handbook | `agent`, with `get_voucher` and `get_rules_in_effect`; reference `compute_wa_voucher` |

## Environment

- Offline and self-contained: `hosts: []`, an empty `.env`, `write: []`, and no clock. Dates are compared
  as day numbers in `world.py`; nothing uses `datetime` at evaluation time.
- Fixtures in `src/plugin/data/` are hand-written: `regimes.json` (the four dated regimes),
  `airports.json`, `travelers.json`, and `scenarios/<id>.json`, which holds facts only and never an
  answer. `request_text` is flavour; every fact it mentions is also a typed field.
- Per diem amounts are real: GSA FY2027 Chicago (October $232 + $92 M&IE), Boston (October $365 + $92),
  and OFM's FY2027 Washington table for Spokane ($126 + $86); each voucher carries the rates for its own stay.
  Carriers, flights, hotels and travelers are fictional. Every regime, every lodging reason, every traveler type
  and every cabin flown occurs in at least one bundled voucher.
- `world.py` (loader, date arithmetic, regime lookup) and `rules.py` (the oracle) are byte-identical in
  `src/plugin/` and `verifier/`.
- Money is int cents and the mileage rate int tenths of a cent: no float anywhere.
- Python 3.12 or later, with dependencies pinned by `uv.lock`.

## Verifier

`verifier/audit.py` reads the fixtures through `Path(__file__)`, computes the oracle with the shared
`rules.py`, and checks the submission in five ordered stages. Each check has a stable reason code. The
message names the first failing check with its rule and numbers (for example "scheduled one-way 600 min
is not > 840 (regime R2024, in effect on departure 2024-12-15)"), and later stages are skipped.

1. **Answer key:** `reference-matches-oracle`.
2. **Referential integrity** (each field is null or 0 exactly when the voucher lacks that part):
   `cabin-matches-air`, `mileage-matches-drives`, `lodging-matches-claim`, `meals-matches-trip`,
   `total-matches-claims`.
3. **Internal consistency:** `cabin-within-flown`, `lodging-amount-fits-basis` (the amount is what the
   stated basis pays for this room), `total-fits-parts` (the total is nights x the submitted nightly amount
   plus the submitted mileage).
4. **Decision against the oracle:** `cabin-correct`, `mileage-correct`, `lodging-basis-correct`,
   `lodging-amount-correct` and `total-correct` (backstops: once the stage-3 fits hold, the basis pins the
   amount and the parts pin the total, so each can fail only together with an earlier decision, never on
   its own).
5. **Flags:** `meals-eligibility-correct`.

`valid` is true only when every constraint holds. `score` is partial credit in [0, 1]: each output field the
voucher makes live is one share (`reimbursable_cabin` when a flight is claimed, `mileage_cents` when a drive
is, `lodging_basis` and `lodging_per_night_cents` when lodging is, `meals_eligible_same_day` on a same-day
trip, `total_reimbursable_cents` when a drive or lodging is), and the score is the fraction of shares equal to
the oracle. Dead fields earn nothing, so the all-null answer scores 0 unless it is the gold audit (it is, on
`seattle-tokyo-seafood` and `seattle-tokyo-ceramics`); a referential-integrity failure describes another
voucher and zeroes the score, as does a broken answer key; wrong by one cent either way scores the same as
wrong by a dollar; `score == 1.0` exactly when `valid`. `details` holds every constraint, the shares and the
expected audit as plain JSON. Shape errors (wrong type, unknown Enum value, missing or extra field, null
for a required field) are refused by NanoAgent's `build_output` before the verifier runs. The verifier is
pure stdlib and never raises: an unexpected value, or an unknown task or tool id, becomes a
`verifier-error` verdict. Tool outputs are also checked against the fixtures (`verify_output`).

## Validation

`tests/` covers the whole required test matrix:

- correct, incorrect, missing and malformed outputs, with malformed cases as `build_output` rejections;
- the signature test: the same 600-min flight is tourist departing 2024-12-15 and business departing
  2025-01-15, and its sharp twin: tourist on 2024-12-31, business on 2025-01-01;
- boundaries, each in unit tests and as bundled twins the agent faces: 480/481 scheduled minutes
  (`seattle-honolulu-fisheries` / `-aquaculture`) and 840/841; departures on 2024-12-31 and 2025-01-01
  (`seattle-tokyo-ceramics` / `-lacquer`); the day before and the day of every mileage change; approval the
  day before vs the day of departure (`chicago-forum-outreach`); 0 vs 1 unused mile; the lodging maximum
  exactly and one cent over; 150% exactly and one cent over (`chicago-forum-king` / `-tower`), with and without
  a listed exception, and a room over the cap clipped to it (`chicago-forum-delegation`); each above-150%
  condition removed; 659/660 and 299/300 meal minutes; half-cent rounding once after the sum, where the
  Honolulu twins' two 61-mile drives give 8845, not 8846;
- partial credit: the score is the fraction of live fields that are right; lazy all-null answers score 0
  except where they are the gold audit; other scenarios' answers never pass; a fabricated part zeroes the
  score; over and under by one cent score the same; the backstops never headline;
- uniqueness: changing any one field of each expected audit to any other value fails with a score below
  1.0. Two vouchers share the whole audit `tourist, 0, null, 0, null, 0` (`seattle-tokyo-seafood` and
  `-ceramics`, both 2024 departures), so a lazy agent that always answers tourist is right on those two and
  wrong on the other twenty-four;
- oracle == the hand-written `tests/cases/<scenario>.json` for every scenario;
- the `rules.py` and `world.py` identity checks; handbook == `instructions`; the handbook's regime table
  == the fixture;
- fixture integrity, recomputing flight minutes with `zoneinfo`; tool-output size under about 1k tokens;
- structured input and output (`tests/test_contract.py`), and `request_text` is flavour only (the oracle
  and the scripted agent give the same answer with it blanked out);
- a cross-policy sanity row shared with the sibling travel-policy plugins: a 360 + 90 + 420 = 870 min
  one-way flight is > 840 and > 480, so business in either regime with advance approval and exhausted
  miles, else tourist;
- a real MCP server round trip, and a scripted, no-LLM run per scenario written from the handbook alone.

## Layout

```text
.
├── nanoagent.yaml   # manifest: id, runtime, permissions, tools, the audit task and its handbook instructions
├── contract.py      # typed inputs and outputs of every tool and the task (Enums, int cents)
├── README.md
├── LICENSE
├── pyproject.toml
├── uv.lock
├── .gitignore
├── .env             # empty: the plugin needs no environment variables
├── src/plugin/      # MCP server (__main__.py), tools, world.py (shared core), rules.py (oracle)
│   └── data/        # handbook.md, regimes.json, airports.json, travelers.json and scenarios/
├── tests/           # verifier matrix, oracle cases, boundaries, scripted agent, tools, fixtures
├── ui/              # renderers.js and renderers.css: outputs drawn from their JSON Schema
├── product/         # product.yaml and icon.svg
└── verifier/        # deterministic verifier: audit.py (task), voucher.py, regimes.py, rules.py, world.py
```

## Develop and run

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
```

To run the agent, use `nanoagent plugin agent config=agent.yaml home=<run folder>` with `arguments` set
to a JSON file such as `{"scenario": "seattle-tokyo-buyers"}`. It needs `OPENROUTER_API_KEY` in the
environment, not in this repo.
