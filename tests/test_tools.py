"""The tools: what they return, what they refuse, how big their outputs are, and the real MCP server."""

import json
import sys

import anyio
import pytest
from helpers import ROOT, SCENARIOS
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from slimconfig import build_output, plain_output

import verifier
from contract import RulesInput, ScenarioInput, VoucherOutput
from plugin import get_rules_in_effect, get_voucher

MAX_OUTPUT_CHARS = 4000  # about 1k tokens: every tool output stays far from the hosted 65,536-token budget


def voucher(scenario):
    return get_voucher(build_output({"scenario": scenario}, ScenarioInput))


def rules(dates):
    return get_rules_in_effect(build_output({"dates": dates}, RulesInput))


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_tool_outputs_match_the_fixtures_and_stay_small(scenario: str) -> None:
    given = build_output({"scenario": scenario}, ScenarioInput)
    found = voucher(scenario)
    assert verifier.verify_output("get_voucher", given, found, ".")["valid"] is True
    assert len(json.dumps(plain_output(found))) <= MAX_OUTPUT_CHARS
    dates = ([found.departure_date] if found.air else []) + [drive.date for drive in found.pov_drives]
    if dates:
        query = build_output({"dates": list(dict.fromkeys(dates))}, RulesInput)
        looked_up = get_rules_in_effect(query)
        assert verifier.verify_output("get_rules_in_effect", query, looked_up, ".")["valid"] is True
        assert len(json.dumps(plain_output(looked_up))) <= MAX_OUTPUT_CHARS


def test_rules_come_back_in_the_order_asked_with_their_windows() -> None:
    found = plain_output(rules(["2026-07-01", "2024-12-31", "2025-01-01"]))["rules"]
    assert [(row["date"], row["regime_id"], row["pov_rate_tenth_cents"]) for row in found] == [
        ("2026-07-01", "R2026B", 760),
        ("2024-12-31", "R2024", 670),
        ("2025-01-01", "R2025", 700),
    ]
    assert found[0]["effective_to"] is None and found[1]["business_over_minutes"] == 840


@pytest.mark.parametrize(
    ("dates", "match"),
    [
        ([], "1 to 6"),
        (["2025-01-01", "2025-01-01"], "each once"),
        (["2023-12-31"], "before 2024-01-01"),
        (["2025-02-29"], "calendar date"),
        (["Jan 1 2025"], "YYYY-MM-DD"),
    ],
)
def test_rules_refuse_bad_input(dates, match) -> None:
    with pytest.raises(ValueError, match=match):
        rules(dates)


def test_a_changed_tool_output_is_caught() -> None:
    given = build_output({"scenario": "seattle-tokyo-2025-01"}, ScenarioInput)
    plain = plain_output(voucher("seattle-tokyo-2025-01"))
    changed = build_output({**plain, "departure_date": "2024-12-15"}, VoucherOutput)
    result = verifier.verify_output("get_voucher", given, changed, ".")
    assert result["valid"] is False and "departure_date" in result["message"]
    query = build_output({"dates": ["2025-01-01"]}, RulesInput)
    wrong = rules(["2024-12-31"])
    assert verifier.verify_output("get_rules_in_effect", query, wrong, ".")["valid"] is False


def test_the_mcp_server_serves_every_tool() -> None:
    async def session():
        server = StdioServerParameters(command=sys.executable, args=["-m", "plugin"], cwd=str(ROOT))
        async with stdio_client(server) as (read, write), ClientSession(read, write) as client:
            await client.initialize()
            names = sorted(tool.name for tool in (await client.list_tools()).tools)
            answer = await client.call_tool("get_voucher", {"scenario": "spokane-new-year-drive"})
            regime = await client.call_tool("get_rules_in_effect", {"dates": ["2026-01-01"]})
            refused = await client.call_tool("get_rules_in_effect", {"dates": []})
            return names, answer, regime, refused

    names, answer, regime, refused = anyio.run(session)
    assert names == ["compute_wa_voucher", "get_rules_in_effect", "get_voucher"]
    assert answer.isError is False and len(answer.structuredContent["pov_drives"]) == 2
    assert regime.isError is False and regime.structuredContent["rules"][0]["regime_id"] == "R2026A"
    assert refused.isError is True
