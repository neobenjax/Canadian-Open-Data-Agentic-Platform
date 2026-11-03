"""Official Canadian open-data connectors."""

from candata_mcp.connectors.boc_valet import ValetClient
from candata_mcp.connectors.ckan_open_canada import (
    CKANClient,
    CKANDatasetDetail,
    CKANDatasetSummary,
    CKANDataStoreResult,
    CKANError,
    CKANHTTPError,
    CKANNotFoundError,
    CKANRequestError,
    CKANResourceSummary,
    CKANResponseError,
    CKANSearchResult,
)
from candata_mcp.connectors.statcan_wds import StatCanAmbiguousMemberError, StatCanClient

__all__ = [
    "CKANClient",
    "CKANDataStoreResult",
    "CKANDatasetDetail",
    "CKANDatasetSummary",
    "CKANError",
    "CKANHTTPError",
    "CKANNotFoundError",
    "CKANRequestError",
    "CKANResourceSummary",
    "CKANResponseError",
    "CKANSearchResult",
    "StatCanAmbiguousMemberError",
    "StatCanClient",
    "ValetClient",
]
