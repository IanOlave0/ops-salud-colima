"""Catálogo mínimo de códigos SCIAN usados en la capa geoespacial de farmacias."""

from __future__ import annotations

from typing import Final

#: Códigos SCIAN oficiales (SCIAN México 2023) para farmacias.
CODIGOS_FARMACIA: Final[dict[str, str]] = {
    "464111": "Farmacias sin minisúper",
    "464112": "Farmacias con minisúper",
}

__all__ = ["CODIGOS_FARMACIA"]
