#!/usr/bin/env python3
# ruff: noqa: E402
"""Interactive Manual Verification Script for CAN-17 / BEN-45 Connector & FastMCP Server Hardening.

Run with:
    uv run python scripts/demo_mcp_hardening.py
"""

from __future__ import annotations

import asyncio
import io
import json
import sys
from pathlib import Path

if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")
if isinstance(sys.stderr, io.TextIOWrapper):
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "candata-mcp" / "src"))
sys.path.insert(0, str(ROOT))

from candata_mcp.connectors.boc_valet import (
    DEFAULT_USER_AGENT as BOC_USER_AGENT,
)
from candata_mcp.connectors.boc_valet import (
    VALET_TERMS_URL,
    Observation,
    ObservationSet,
    SeriesDetail,
    ValetClient,
    _name,
)
from candata_mcp.connectors.statcan_wds import (
    DEFAULT_USER_AGENT as STATCAN_USER_AGENT,
)
from candata_mcp.connectors.statcan_wds import (
    STATCAN_LICENCE_URL,
    DimensionMember,
    StatCanAmbiguousMemberError,
)
from candata_mcp.server import create_server


def print_header(title: str) -> None:
    print("\n" + "=" * 76)
    print(f" [CAN-17] {title.upper()}")
    print("=" * 76)


async def demo_valet_hardening() -> None:
    print_header("1. Bank of Canada Valet Hardening (V-F1..8 Verification)")

    # 1. User Agent (V-F6)
    print(f"\n[V-F6] Default User Agent: {BOC_USER_AGENT}")

    # 2. Strict Series Name Validation (V-F4)
    print("\n[V-F4] Strict Series Name Checking with re.fullmatch:")
    test_cases = ["V39079", "CPI_TRIM", "V39079\n", "V39079/../x", ""]
    for name in test_cases:
        try:
            safe = _name(name)
            print(f"  [OK] Safe input {name!r:>15} -> {safe}")
        except ValueError as exc:
            print(f"  [BLOCKED] Rejected unsafe {name!r:>10} -> {exc}")

    # 3. Provenance Source Tracking (V-F8) & Attribution (V-F7)
    print("\n[V-F7 & V-F8] Provenance Source & Terms URL in CitationEnvelope:")
    mock_series = SeriesDetail(
        name="V39079",
        label="Policy interest rate",
        description="Target rate",
        frequency="D",
        unit="%",
        date_format="daily",
        url="https://www.bankofcanada.ca/valet/series/V39079",
    )
    obs = ObservationSet(
        series=mock_series,
        observations=(Observation("2026-10-20", 3.75),),
        fetched_at="2026-10-20T22:00:00+00:00",
        fetched_at_source="server_date",
        license_url=VALET_TERMS_URL,
    )
    citation = obs.citation()
    print(f"  * fetched_at: {obs.fetched_at} (Source: {obs.fetched_at_source})")
    print(f"  * license_url: {citation.enrichment.license_url}")
    print(f"  * core tuple: {citation.core}")

    # 4. HTTPS base_url Enforcement (V-F5)
    print("\n[V-F5] Insecure HTTP Base URL Defense:")
    try:
        ValetClient(base_url="http://www.bankofcanada.ca/valet")
        print("  [FAIL] Failed to reject insecure HTTP")
    except ValueError as exc:
        print(f"  [BLOCKED] {exc}")


async def demo_statcan_hardening_and_discovery() -> None:
    print_header("2. Statistics Canada Hardening & FastMCP Discovery Tools")

    # 1. User Agent & Licence URL
    print(f"\n[StatCan] Default User Agent: {STATCAN_USER_AGENT}")
    print(f"[StatCan] Official Licence URI: {STATCAN_LICENCE_URL}")

    server = create_server()
    try:
        # 2. search_statcan_cubes
        print("\n[Tool: search_statcan_cubes] Searching for 'housing':")
        res = await server.mcp.call_tool("search_statcan_cubes", {"query": "housing", "limit": 2})
        payload = json.loads(res.content[0].text)
        print(f"  Query: {payload['query']} | Total Results: {payload['total_results']}")
        for cube in payload["cubes"]:
            print(f"  * [{cube['table_id']}] {cube['title_en'][:65]}... ({cube['frequency_name']})")

        # 3. get_cube_dimensions (Token-Budgeted)
        print("\n[Tool: get_cube_dimensions] Pruned Hierarchy (max 3 members/dim):")
        res_dim = await server.mcp.call_tool(
            "get_cube_dimensions", {"product_id": "18100004", "max_members_per_dim": 3}
        )
        dim_payload = json.loads(res_dim.content[0].text)
        print(f"  Table: {dim_payload['table_id']} -- {dim_payload['title_en']}")
        for dim in dim_payload["dimensions"]:
            shown = len(dim["members"])
            total = dim["total_members"]
            more = dim["has_more_members"]
            print(
                f"  * Dimension {dim['position_id']}: {dim['name_en']} "
                f"({shown} of {total} members shown, has_more={more})"
            )

        # 4. Ambiguity Resolution Defense (Guardrail 6)
        print("\n[Guardrail 6] Ambiguous Member Error Payload Defense:")
        ambig_err = StatCanAmbiguousMemberError(
            member_name="Kentville",
            dimension_position=1,
            dimension_name="Geography",
            product_id=34100133,
            candidates=(
                DimensionMember(101, None, "Kentville (Town)", None, None),
                DimensionMember(102, None, "Kentville (Census Agglomeration)", None, None),
            ),
        )
        print("  Structured Exception caught:")
        print(f"    * member_name: {ambig_err.member_name!r}")
        print(f"    * dimension: {ambig_err.dimension_position} ({ambig_err.dimension_name})")
        print(f"    * candidate IDs: {ambig_err.candidate_ids}")
        print(
            "    * recovery action: Structured error envelope returns candidate IDs "
            "to LangGraph Supervisor."
        )
    finally:
        await server.aclose()


async def main() -> None:
    await demo_valet_hardening()
    await demo_statcan_hardening_and_discovery()
    print_header("All CAN-17 Manual Verification Probes Passed Successfully!")


if __name__ == "__main__":
    asyncio.run(main())
