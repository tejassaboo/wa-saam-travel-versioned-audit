# WA SAAM Travel Versioned Audit

A `nanoagent.plugin/v0001` plugin. An agent audits one Washington State travel voucher under a toy
handbook paraphrased from SAAM Chapter 10 (Travel) and OFM Directives 25A-01, 26A-01 and 26A-05. The
rules changed over time, so the agent must use the rules in force on the right date. It reads the
voucher, looks up the rule regime for the dates that matter, and submits a typed audit. A deterministic
Python verifier, with no LLM, checks the audit against an oracle that it computes itself.

## Task

- **Input:** `ScenarioInput` with a single field, `scenario`, which names one of sixteen bundled vouchers,
  for example `{"scenario": "seattle-tokyo-buyers"}`.
- **Tools:** the agent calls `get_voucher`, then `get_rules_in_effect` once (skipped when no date
  matters), then `submit`. That is at most three of the six hosted steps.
- **Output:** `WaVoucherOutput`, with these fields:
  - `reimbursable_cabin`: `tourist` or `business`, or null when no airfare is claimed;
  - `mileage_cents`: POV mileage in integer USD cents;
  - `lodging_basis`: `within_max`, `exception_150`, `above_150_conference` or `capped_at_max`, or null;
  - `lodging_per_night_cents`: integer USD cents;
  - `meals_eligible_same_day`: true or false on a same-day trip, null on an overnight trip.
- **Success:** the audit equals the one audit that the handbook's rules give.

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

Each scenario sets one trap:

| Scenario | Trap | Correct audit |
|---|---|---|
| `seattle-tokyo-seafood` | A 600-min flight to Tokyo departing 2024-12-15, approved, miles exhausted | tourist (600 is not > 840) |
| `seattle-tokyo-buyers` | The same flight departing 2025-01-15, but booked and approved in 2024 | business (600 > 480) |
| `seattle-tokyo-apples` | Business approved after the trip | tourist |
| `seattle-tokyo-health` | 40,000 state miles still unspent | tourist |
| `olympia-honolulu-reef` | In-air 455 min, but 625 scheduled with the connection | business; mileage 8540 |
| `boston-transport-session` | First class on a domestic flight; room under the maximum | tourist; within_max 32900 |
| `yakima-riparian-plots` | 311 mi at $0.725 (half cent); exactly 11 h | mileage 22548; meals true |
| `yakima-plot-followup` | 311 mi on the day $0.76 starts; 10 h 59 min | mileage 23636; meals false |
| `millersylvania-debris-cleanup` | A volunteer on the eve of 25A-01; exactly 5 h | mileage 5829; meals true |
| `spokane-arena-inspection` | Drives on 2025-12-31 and 2026-01-01; the note asks for one rate | mileage 45743 |
| `spokane-crane-audit` | A listed reason, never approved | capped_at_max 12600; mileage 48792 |
| `chicago-forum-lakeshore` | Venue hotel $410, approved; cap is 150% of lodging plus M&IE | exception_150 41000; tourist; mileage 9272 |
| `chicago-forum-colleague` | Approved, but loyalty points are not a listed reason | capped_at_max 23200 |
| `chicago-forum-king` | The room costs exactly 150% ($486.00); attendance required, lowest advertised rate documented at $486.00 | exception_150 48600 |
| `chicago-forum-tower` | The same stay one cent over ($486.01, also the lowest advertised rate); the note offers to be clipped to $486.00 | above_150_conference 48601 |
| `boston-state-auditors` | Every above-150% condition holds, but a pricier room than the lowest advertised was booked | above_150_conference 70500 |

## Tools

| Tool | Does | Code |
|---|---|---|
| `get_voucher` | Returns a scenario's voucher: the traveler's note, traveler type, trip dates, the one-way flight (segments, scheduled one-way minutes, cabin flown, approval date, unused miles), POV drives and lodging | `src/plugin/voucher.py` |
| `get_rules_in_effect` | Returns the rule regime (business threshold, mileage rate, window, directive) in effect on each of 1–6 dates. It applies no policy: which date governs is the agent's call | `src/plugin/regimes.py` |
| `compute_wa_voucher` | The answer key: the oracle (`rules.oracle`) over the bundled fixtures. It is the task's `reference`, never shown to the agent | `src/plugin/reference.py` |

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
  and OFM's FY2027 Washington table for Spokane ($126 + $86). Carriers, flights, hotels and travelers are
  fictional.
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
   `cabin-matches-air`, `mileage-matches-drives`, `lodging-matches-claim`, `meals-matches-trip`.
3. **Internal consistency:** `cabin-within-flown`, `lodging-amount-fits-basis` (the amount is what the
   stated basis pays for this room).
4. **Decision against the oracle:** `cabin-correct`, `mileage-correct`, `lodging-basis-correct`,
   `lodging-amount-correct`.
5. **Flags:** `meals-eligibility-correct`.

The score is 1.0 when the audit is valid and 0.0 otherwise; `details` holds every constraint and the
expected audit as plain JSON. Shape errors (wrong type, unknown Enum value, missing or extra field, null
for a required field) are refused by NanoAgent's `build_output` before the verifier runs. The verifier is
pure stdlib and never raises: an unexpected value, or an unknown task or tool id, becomes a
`verifier-error` verdict. Tool outputs are also checked against the fixtures (`verify_output`).

## Validation

`tests/` covers the brief's whole test matrix:

- correct, incorrect, missing and malformed outputs, with malformed cases as `build_output` rejections;
- the signature test: the same 600-min flight is tourist departing 2024-12-15 and business departing
  2025-01-15;
- boundaries: 480/481 and 840/841 minutes; departures on 2024-12-31 and 2025-01-01; the day before and
  the day of every mileage change; approval the day before vs the day of departure; 0 vs 1 unused mile;
  the lodging maximum exactly and one cent over; 150% exactly and one cent over, with and without a
  listed exception, and as a bundled twin pair (`chicago-forum-king` / `chicago-forum-tower`) that changes
  the basis; each above-150% condition removed; 659/660 and 299/300 meal minutes; half-cent
  rounding (121 miles at $0.725);
- uniqueness: changing any one field of each expected audit to any other value fails;
- oracle == the hand-written `tests/cases/<scenario>.json` for every scenario;
- the `rules.py` and `world.py` identity checks; handbook == `instructions`; the handbook's regime table
  == the fixture;
- fixture integrity, recomputing flight minutes with `zoneinfo`; tool-output size under about 1k tokens;
- structured input and output (`tests/test_contract.py`), and `request_text` is flavour only (the oracle
  and the scripted agent give the same answer with it blanked out);
- the brief's §11 cross-policy row for WA SAAM: 360 + 90 + 420 = 870 > 840 and > 480 gives business in
  either regime with advance approval and exhausted miles, else tourist;
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
