"""Shared fixtures: parse and chunk the test book once per session."""

import sys
from pathlib import Path

import pytest

# Make `app` importable when pytest runs from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config
from app.parser import parse_pdf
from app.chunker import chunk_book


@pytest.fixture(scope="session")
def book():
    return parse_pdf(config.TEST_PDF)


@pytest.fixture(scope="session")
def chunked(book):
    return chunk_book(book)
