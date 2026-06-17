from __future__ import annotations

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT.parent / "openart-tools" / "document.extract_pdf_text" / "scripts"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from document_extract_pdf_text import _looks_like_text


def test_document_text_filter_accepts_readable_ocr_output() -> None:
    text = """TOTAL BALANCE DUE\n$223.99\nPAID WITH MASTERCARD\n"""

    assert _looks_like_text(text)


def test_document_text_filter_rejects_binaryish_long_line() -> None:
    text = "JDNIGAYNDADNVIVEIVLOL" * 80

    assert not _looks_like_text(text)
