"""English/French selection for official titles (CAN-26).

Statistics Canada publishes French titles for every cube and series; the Bank of Canada does
not (Valet has no ``?lang=fr``), so French comes only from the sourced ``FRENCH_TITLES`` table.
This module never translates. When the requested language is missing it falls back to English
and says so, so an answer can't pass an English title off as the French one.
"""

from dataclasses import dataclass
from typing import Any, Literal

from candata_mcp.citation import BilingualTitle

Language = Literal["en", "fr"]


def parse_language(value: str | None) -> Language:
    """Accept ``en``, ``fr`` and case or region variants such as ``FR-CA``."""
    if value is None:
        return "en"
    code = value.strip().lower().replace("_", "-").split("-")[0]
    if code == "en":
        return "en"
    if code == "fr":
        return "fr"
    raise ValueError(f"Unsupported language '{value}'. Use 'en' or 'fr'.")


@dataclass(frozen=True, slots=True)
class LocalizedTitle:
    text: str
    language: Language
    requested: Language
    fallback: bool

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "title": self.text,
            "language": self.language,
            "requested": self.requested,
            "fallback": self.fallback,
        }
        if self.fallback:
            payload["note"] = "No official French title is published; showing the English title."
        return payload


def localize_title(title: BilingualTitle, lang: Language) -> LocalizedTitle:
    """Pick the title in ``lang``, falling back to English when French is missing or empty."""
    if lang == "fr":
        if title.fr and title.fr.strip():
            return LocalizedTitle(title.fr, "fr", "fr", fallback=False)
        return LocalizedTitle(title.en, "en", "fr", fallback=True)
    return LocalizedTitle(title.en, "en", "en", fallback=False)
