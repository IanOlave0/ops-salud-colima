"""Catálogo mínimo de códigos SCIAN usados en la capa geoespacial de farmacias."""

from __future__ import annotations
from typing import Final

#: Códigos SCIAN oficiales (SCIAN México 2023) para farmacias.
CODIGOS_FARMACIA: Final[dict[str, str]] = {
    "464111": "Farmacias sin minisúper",
    "464112": "Farmacias con minisúper",
}

__all__ = ["CODIGOS_FARMACIA"]
import unittest
from src.e2.catalogo_scian import CODIGOS_FARMACIA

class TestCatalogoSCIAN(unittest.TestCase):
    def test_codigos_esperados(self):
        self.assertIn("464111", CODIGOS_FARMACIA)
        self.assertIn("464112", CODIGOS_FARMACIA)

    def test_etiquetas_no_vacias(self):
        for codigo, etiqueta in CODIGOS_FARMACIA.items():
            self.assertIsInstance(codigo, str)
            self.assertEqual(len(codigo), 6)
            self.assertIsInstance(etiqueta, str)
            self.assertTrue(etiqueta.strip())

    def test_sin_codigos_extra(self):
        self.assertEqual(set(CODIGOS_FARMACIA.keys()), {"464111", "464112"})

if __name__ == "__main__":
    unittest.main()