"""Stress-testing script for CAN-17 (PR #33) review feedback resolution.

Validates all 3 of Samir Ibrahim's blocking review observations against live logic:
1. get_cube_dimensions can reach Toronto (memberId 125) via member_query and offset paging.
2. search_statcan_cubes tokenizes multi-word queries ('toronto rent', 'two bedroom rent'),
   respects word boundaries ('rent' does not match 'current'), and returns true total_results.
3. FALLBACK_CUBES_LITE is eliminated and outages produce clean STATCAN_UNAVAILABLE errors.
"""

from __future__ import annotations

import asyncio
import io
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "packages" / "candata-mcp" / "src"))

# ruff: noqa: E402
from candata_mcp.connectors.statcan_wds import (
    CubeMetadata,
    Dimension,
    DimensionMember,
    StatCanUnavailableError,
)
from candata_mcp.server import CanDataServer


async def stress_test() -> None:
    print("=" * 76)
    print(" 🍁 STRESS-TESTING PR #33 RESOLUTION AGAINST SAMIR'S REVIEW COMMENTS")
    print("=" * 76)

    server = CanDataServer()
    client = server.statcan_client

    # -------------------------------------------------------------------------
    # Observation 1: get_cube_dimensions can't reach Toronto (Geography > 100)
    # -------------------------------------------------------------------------
    print("\n[STRESS 1] Validating get_cube_dimensions member search & pagination...")

    # Build 247 mock geography members mimicking 34-10-0133-01 where Toronto is #160 (id 125)
    geo_members = [
        DimensionMember(i, None, f"Municipality {i}", f"Municipalité {i}", None)
        for i in range(1, 248)
    ]
    geo_members[159] = DimensionMember(125, None, "Toronto, Ontario", "Toronto, Ontario", None)
    geo_members[200] = DimensionMember(
        150, None, "Ottawa-Gatineau, Ontario/Quebec", "Ottawa-Gatineau", None
    )

    mock_34100133 = CubeMetadata(
        product_id=34100133,
        cansim_id="027-0040",
        title_en="CMHC average rents for areas with a population of 10,000 and over",
        title_fr="SCHL loyers moyens",
        start_date="1987-01-01",
        end_date="2025-01-01",
        release_time="2025-01-15T08:30",
        frequency_code=12,
        frequency_name="annual",
        dimensions=(
            Dimension(1, "Geography", "Géographie", False, tuple(geo_members)),
            Dimension(
                2,
                "Type of structure",
                "Type de structure",
                False,
                (
                    DimensionMember(1, None, "Row", "Rangée", None),
                    DimensionMember(2, None, "Apartment", "Appartement", None),
                ),
            ),
        ),
    )
    client.get_cube_metadata = AsyncMock(return_value=mock_34100133)

    # 1a. Test member_query="Toronto"
    res1a = await server.mcp.call_tool(
        "get_cube_dimensions", {"product_id": "34100133", "member_query": "Toronto"}
    )
    p1a = json.loads(res1a.content[0].text)
    dim_geo = p1a["dimensions"][0]

    assert dim_geo["total_members"] == 247
    assert dim_geo["matched_members_count"] == 1
    assert len(dim_geo["members"]) == 1
    assert dim_geo["members"][0]["member_id"] == 125
    assert dim_geo["members"][0]["name_en"] == "Toronto, Ontario"
    print(" ✅ member_query='Toronto' successfully retrieved Toronto (memberId 125) from 247!")

    # 1b. Test pagination offset=150, limit=15 (without query)
    res1b = await server.mcp.call_tool(
        "get_cube_dimensions", {"product_id": "34100133", "offset": 150, "limit": 15}
    )
    p1b = json.loads(res1b.content[0].text)
    dim_geo_b = p1b["dimensions"][0]
    assert dim_geo_b["offset"] == 150
    assert dim_geo_b["limit"] == 15
    assert len(dim_geo_b["members"]) == 15
    # Item 160 is at index 9 within this slice (150 + 9 = 159)
    assert dim_geo_b["members"][9]["member_id"] == 125
    assert dim_geo_b["members"][9]["name_en"] == "Toronto, Ontario"
    print(" ✅ Pagination offset=150, limit=15 reached position 160 (Toronto) successfully!")

    # -------------------------------------------------------------------------
    # Observation 2: search_statcan_cubes multi-word matching & true match count
    # -------------------------------------------------------------------------
    print("\n[STRESS 2] Validating search_statcan_cubes tokenized word-boundary matching...")

    catalog = [
        {
            "productId": 34100133,
            "cansimId": "027-0040",
            "cubeTitleEn": (
                "Canada Mortgage and Housing Corporation, average rents for areas "
                "with a population of 10,000 and over, two bedroom units"
            ),
            "cubeTitleFr": "Société canadienne d'hypothèques et de logement, loyers moyens",
            "cubeStartDate": "1987-01-01",
            "cubeEndDate": "2025-01-01",
            "releaseTime": "2025-01-15T08:30",
            "frequencyCode": 12,
        },
        {
            "productId": 18100004,
            "cansimId": "326-0020",
            "cubeTitleEn": "Consumer Price Index, monthly, not seasonally adjusted, shelter, rent",
            "cubeTitleFr": "Indice des prix à la consommation, mensuel, logement, loyer",
            "cubeStartDate": "1914-01-01",
            "cubeEndDate": "2026-09-01",
            "releaseTime": "2026-10-20T08:30",
            "frequencyCode": 6,
        },
        {
            "productId": 10100001,
            "cansimId": "100-0001",
            "cubeTitleEn": "Current account and capital account, international investment position",
            "cubeTitleFr": "Compte courant et compte de capital",
            "cubeStartDate": "1990-01-01",
            "cubeEndDate": "2025-01-01",
            "releaseTime": "2025-01-15T08:30",
            "frequencyCode": 7,
        },
    ]
    client.get_all_cubes_list_lite = AsyncMock(return_value=catalog)

    # 2a. Multi-word: "housing rent"
    s_rent = await server.mcp.call_tool("search_statcan_cubes", {"query": "housing rent"})
    p_rent = json.loads(s_rent.content[0].text)
    assert p_rent["total_results"] == 1
    assert p_rent["cubes"][0]["product_id"] == 34100133
    print(" ✅ Multi-word query 'housing rent' matched 34-10-0133-01!")

    # 2b. Multi-word: "two bedroom rent"
    s_2bed = await server.mcp.call_tool("search_statcan_cubes", {"query": "two bedroom rent"})
    p_2bed = json.loads(s_2bed.content[0].text)
    assert p_2bed["total_results"] == 1
    assert p_2bed["cubes"][0]["product_id"] == 34100133
    print(" ✅ Multi-word query 'two bedroom rent' matched 34-10-0133-01!")

    # 2c. Word boundary check: "rent" matches 34100133 & 18100004, rejects 10100001 ("current")
    s_boundary = await server.mcp.call_tool("search_statcan_cubes", {"query": "rent"})
    p_boundary = json.loads(s_boundary.content[0].text)
    assert p_boundary["total_results"] == 2
    matched_pids = {c["product_id"] for c in p_boundary["cubes"]}
    assert 10100001 not in matched_pids, "Failure: 'rent' matched 'current account'!"
    assert 34100133 in matched_pids and 18100004 in matched_pids
    print(" ✅ Word boundary check: 'rent' matched CMHC & CPI, rejected 'current account'!")

    # 2d. True total_results pagination count
    s_page = await server.mcp.call_tool("search_statcan_cubes", {"query": "rent", "limit": 1})
    p_page = json.loads(s_page.content[0].text)
    assert p_page["total_results"] == 2
    assert len(p_page["cubes"]) == 1
    print(" ✅ Pagination count check: total_results reflects 2 while page length is 1!")

    # -------------------------------------------------------------------------
    # Observation 3: FALLBACK_CUBES_LITE eliminated & clean outage errors
    # -------------------------------------------------------------------------
    print("\n[STRESS 3] Validating FALLBACK_CUBES_LITE elimination and outage error handling...")

    # Assert FALLBACK_CUBES_LITE is not defined in statcan_wds module
    import candata_mcp.connectors.statcan_wds as statcan_module

    assert not hasattr(statcan_module, "FALLBACK_CUBES_LITE"), (
        "Failure: FALLBACK_CUBES_LITE still exists!"
    )
    print(" ✅ Confirmed FALLBACK_CUBES_LITE has been completely removed from module scope.")

    # Simulate WDS outage
    client.get_all_cubes_list_lite = AsyncMock(
        side_effect=StatCanUnavailableError("WDS catalog connection timeout", retry_after=30)
    )
    s_outage = await server.mcp.call_tool("search_statcan_cubes", {"query": "cpi"})
    p_outage = json.loads(s_outage.content[0].text)
    assert p_outage["isError"] is True
    assert p_outage["error_code"] == "STATCAN_UNAVAILABLE"
    assert p_outage["retry_after"] == 30
    assert "suggested_action" in p_outage
    print(" ✅ Outage produced structured STATCAN_UNAVAILABLE payload with retry guidance.")

    print("\n" + "=" * 76)
    print(" 🍁 ALL STRESS TESTS PASSED: SAMIR'S 3 BLOCKING OBSERVATIONS ARE 100% RESOLVED!")
    print("=" * 76)


if __name__ == "__main__":
    asyncio.run(stress_test())
