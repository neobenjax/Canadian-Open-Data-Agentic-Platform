"""CanData-MCP: Canadian official open-data connectors with verifiable citations."""

from candata_mcp.citation import (
    BilingualTitle,
    CitationEnvelope,
    CoreVerificationTuple,
    MetadataEnrichment,
)
from candata_mcp.connectors import StatCanAmbiguousMemberError, StatCanClient, ValetClient
from candata_mcp.engine import DuckDBSlicingEngine

__all__ = [
    "BilingualTitle",
    "CitationEnvelope",
    "CoreVerificationTuple",
    "DuckDBSlicingEngine",
    "MetadataEnrichment",
    "StatCanAmbiguousMemberError",
    "StatCanClient",
    "ValetClient",
]
