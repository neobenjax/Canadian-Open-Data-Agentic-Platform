import os

# Normalize NO_PROXY / no_proxy to remove bracketed IPv6 entries (e.g. '[::1]') which cause
# httpx URLPattern parsing to raise InvalidURL('Invalid port: :1]') on Linux/container environments.
for _var in ("NO_PROXY", "no_proxy"):
    if _val := os.environ.get(_var):
        if "[::1]" in _val:
            os.environ[_var] = ",".join(p.strip() for p in _val.split(",") if p.strip() != "[::1]")

from candata_mcp.citation import (  # noqa: E402
    BilingualTitle,
    CitationEnvelope,
    CoreVerificationTuple,
    MetadataEnrichment,
)
from candata_mcp.connectors import (  # noqa: E402
    StatCanAmbiguousMemberError,
    StatCanClient,
    ValetClient,
)
from candata_mcp.engine import DuckDBSlicingEngine  # noqa: E402

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
