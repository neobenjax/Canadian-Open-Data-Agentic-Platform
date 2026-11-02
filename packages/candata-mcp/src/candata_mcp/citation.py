"""Two-tier citation envelope returned alongside every official figure.

Field names, nesting and reference-period formats mirror ``CitationEnvelope`` in
``collaboration/benchmarks/build_ground_truth.py`` (CAN-14), so benchmark answers and
connector output can be compared field by field. Connectors import it from here, which
keeps one place to swap if the shared model is moved or redefined.

Tier 1 (``CoreVerificationTuple``) is strict pass/fail. Tier 2 (``MetadataEnrichment``)
is scored; a missing field lowers the score but never fails an answer.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BilingualTitle:
    en: str
    fr: str | None


@dataclass(frozen=True, slots=True)
class CoreVerificationTuple:
    """``reference_period`` is ``2025``, ``2025-10``, ``2025-01-30`` or ``start/end``."""

    table_id: str
    vector_id: str
    reference_period: str


@dataclass(frozen=True, slots=True)
class MetadataEnrichment:
    coordinate: str | None
    release_or_revision_date: str | None
    bilingual_title: BilingualTitle
    canonical_url: str
    license_url: str | None = None


@dataclass(frozen=True, slots=True)
class CitationEnvelope:
    publisher: str
    core: CoreVerificationTuple
    enrichment: MetadataEnrichment
