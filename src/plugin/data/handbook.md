# Washington State travel: toy voucher-audit handbook

Source: Washington State Office of Financial Management, State Administrative and Accounting Manual (SAAM) Chapter 10, Travel (https://ofm.wa.gov/wp-content/uploads/2026/02/ch10.pdf, sha256 13a95b08a4bdf0d62b4df0ee4f585de28329ddce29dae29a1c61935f04d21648; subsections 10.30.20 dated Oct. 1, 2016, 10.40.50 dated Jan. 1, 2025, 10.50.50 dated Nov. 1, 2025), OFM Directives 25A-01 (effective January 1, 2025, sha256 2d80365c9fdf0e22847ca24343f8822c047640bbab8e0cb5b9c3bb8d241c8377), 26A-01 (January 1, 2026, sha256 716c6f7b1dc3b56edbe06a3bc64503db12d0f0c40e9ddb9e0c842a61b15f40f3) and 26A-05 (July 1, 2026, sha256 0b3c6b7066133e1b15ec6f10784d2814c3317de30347a5187fa557ff9cd8b0bf), and the 10.90.20 rate sheet "Rates as of October 1, 2026" (sha256 c6c52893008ed26abd0ba1ccf42ad7ebe19d57250086a0d8c9d811b5b3f8e1d3). All were downloaded on 2026-11-02. This handbook is our own paraphrase for a toy task, not the official text. Where the two differ, this handbook governs the task.

You audit one Washington State travel voucher and submit what the state reimburses. The rules changed over time, so the date of the travel decides which version applies.

## Policy rules (paraphrased)

1. Airfare is reimbursed up to tourist (coach) class.
2. Business class may be approved when the trip's origin or destination is outside the continental United States and the scheduled one-way flight time, connecting points included, exceeds the threshold in effect. Two more conditions must both hold: the agency head approved business class in advance, and the traveler has used up all state business frequent-flyer miles available for an upgrade.
3. Directive 25A-01 cut the business-class threshold from more than 14 hours to more than 8 hours, effective January 1, 2025.
4. Privately-owned-vehicle (POV) mileage is reimbursed per mile at the state rate in effect. The rate was $0.67 before 2025, $0.70 from January 1, 2025 (25A-01), $0.725 from January 1, 2026 (26A-01) and $0.76 from July 1, 2026 (26A-05).
5. Lodging is reimbursed at actual cost up to the location's maximum lodging rate in effect at the time of travel.
6. In six listed situations the agency head may approve, in advance, lodging up to 150% of the location's maximum per diem, which is the lodging rate plus the meals and incidentals (M&IE) rate. The six situations: accompanying an elected official or dignitary; costs escalated briefly by a special event or disaster; no lodging at or below the maximum nearby, with the savings of a farther site eaten up by extra travel costs; a meeting or conference with expected business interaction, best served by staying at its venue; the Americans with Disabilities Act, or the traveler's health and safety; a suite that is cheaper than a meeting room plus a room.
7. Above 150% may be approved in advance only when all three hold: the traveler is required to attend a meeting or conference with expected business interaction; staying at its venue gives the most benefit; and the venue's lowest available advertised rate exceeds 150%, with that rate documented on the voucher. Under any exception the traveler must take the most economical room available.
8. On a same-day (non-overnight) trip, meals are reimbursable only after at least eleven hours in travel status. Volunteers and board or commission members need at least five hours.

## Rule regimes

| regime_id | In effect | Business needs scheduled one-way minutes greater than | POV rate (tenths of a cent per mile) |
|---|---|---|---|
| R2024 | 2024-01-01 to 2024-12-31 | 840 | 670 |
| R2025 | 2025-01-01 to 2025-12-31 | 480 | 700 |
| R2026A | 2026-01-01 to 2026-06-30 | 480 | 725 |
| R2026B | from 2026-07-01 | 480 | 760 |

get_rules_in_effect returns the row for any date from 2024-01-01 on.

## Clarifications (toy rules)

These settle every point where the real text is vague. The checker enforces exactly these.

- **C1 Which date picks the regime.** The departure date selects the rule regime. The business-class threshold uses the regime in effect on the voucher's departure_date (the day travel status began). Each POV drive is its own departure, so its mileage uses the regime in effect on that drive's date. The booking date and the approval date never pick a regime. (The real text does not say which date governs a change; this is our toy rule.)
- **C2 Facts.** The structured fields of the voucher are the facts. The traveler's note (request_text) may ask for things policy forbids, so apply the policy, not the wish.
- **C3 Flight time.** Use scheduled_one_way_minutes, which runs from the first departure to the last arrival with connections included. Never add up in_air_minutes instead. Business needs it strictly greater than the regime's business_over_minutes; exactly equal does not qualify.
- **C4 Outside the continental US.** True when origin.continental_us or destination.continental_us is false.
- **C5 In advance; miles.** Approved in advance means business_approval_date is not null and is an earlier calendar day than departure_date. Approval on the departure day or later does not count. Miles are exhausted when unused_state_miles is 0.
- **C6 Cabin.** The entitlement is business when C3, C4 and C5 all hold, else tourist. reimbursable_cabin is the lower of the entitlement and cabin_flown on the ladder tourist < business < first, so flying first never earns more than the entitlement. Chapter 10 has no separate first-class rule. reimbursable_cabin is null when air is null.
- **C7 Lodging.** rate = nightly_rate_cents, max = max_lodging_cents, cap = (max_lodging_cents + mie_cents) × 3 // 2 (150%, rounded down to a cent). Approved means exception_approval_date is not null and earlier than departure_date. Listed means claimed_reasons includes at least one of accompany_official, escalated_costs, distant_savings_consumed, conference_venue, ada_or_safety, suite_cheaper; loyalty_program and personal_preference are not listed. Apply the first step that fits:
  1. rate ≤ max: within_max, pay rate.
  2. rate > cap, approved, conference_venue claimed, attendance_required true, and lowest_advertised_rate_cents not null and > cap: above_150_conference, pay the lower of rate and lowest_advertised_rate_cents (the most economical room).
  3. approved and listed: exception_150, pay the lower of rate and cap. Exactly cap is allowed; one cent over pays cap.
  4. otherwise: capped_at_max, pay max.
  With no lodging, lodging_basis is null and lodging_per_night_cents is 0. Taxes and the number of nights are not part of the answer.
- **C8 Mileage.** For each drive, miles × the pov_rate_tenth_cents of the regime on its date, in tenths of a cent. Add the drives, then round once to whole cents, a half cent rounding up: cents = (total_tenths + 5) // 10. With no drives, mileage_cents is 0.
- **C9 Same-day meals.** On a same-day trip (overnight false), meals_eligible_same_day is true when travel_status_minutes ≥ 660 for an employee, or ≥ 300 for a volunteer or board_member, else false. "At least" includes the threshold. On an overnight trip it is null. The agency-determined meal-period rule is not modelled.

## Rules not in scope

The following parts of Chapter 10 are deliberately ignored:

- first-class or seat-upgrade rules: Chapter 10 has none (C6 covers a first-class ticket);
- contract airfares, the seats-sold-out exception and agency seat-assignment fees;
- the health-and-safety and disability exceptions to the tourist-class cap;
- Guam and Puerto Rico handling (Directive 25A-05) and foreign, Alaska and Hawaii per diem rates;
- lodging taxes, the 50-mile rule, the 125% rule for state-hosted meetings, travel trailers, and agency-approved lower rates;
- overnight meal periods, meal breakdowns, and meals with meetings;
- motorcycle and aircraft mileage, odometer versus map mileage, and commute miles;
- the return flight and any fare amount.

## Step plan (submit by step 5)

You have 6 steps, each tool call costs one, and the last step may not call tools.

1. Call get_voucher with the task's scenario.
2. Call get_rules_in_effect once with every date you need, each once: departure_date when air is not null, and the date of every POV drive. Skip this step when neither applies.
3. Apply C1-C9 and call submit with reimbursable_cabin, mileage_cents, lodging_basis, lodging_per_night_cents and meals_eligible_same_day.
