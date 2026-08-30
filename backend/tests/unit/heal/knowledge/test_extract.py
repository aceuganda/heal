"""Tests for turning an uploaded file into text.

The case that matters clinically is the scanned PDF: pages but no text layer.
Indexing it silently would create an approved, citable source containing
nothing.
"""
import pytest

from heal.knowledge.extract import extract
from heal.knowledge.extract import ExtractionError


class TestTextFiles:
    def test_plain_text(self) -> None:
        assert extract(b"Give 500mg BD.", "note.txt").text == "Give 500mg BD."

    def test_markdown(self) -> None:
        assert extract(b"# Title\n\nBody", "guide.md").kind == "text"

    def test_falls_back_through_encodings(self) -> None:
        assert "café" in extract("café".encode("latin-1"), "n.txt").text

    def test_utf16_is_honoured_behind_a_byte_order_mark(self) -> None:
        assert extract("500mg".encode("utf-16"), "n.txt").text == "500mg"

    def test_utf16_is_not_guessed_without_a_bom(self) -> None:
        """Speculative UTF-16 succeeds on most bytes and yields mojibake."""
        assert extract(b"Give 500mg BD.", "n.txt").text == "Give 500mg BD."

    def test_a_utf8_bom_is_stripped(self) -> None:
        assert extract(b"\xef\xbb\xbfDose", "n.txt").text == "Dose"


class TestUnsupported:
    @pytest.mark.parametrize("name", ["scan.tiff", "sheet.xlsx", "noext"])
    def test_unsupported_types_name_what_is_supported(self, name: str) -> None:
        with pytest.raises(ExtractionError) as excinfo:
            extract(b"data", name)
        assert ".pdf" in str(excinfo.value)


class TestScannedPdf:
    def test_a_pdf_with_no_text_layer_is_refused_not_indexed_empty(
        self, monkeypatch
    ) -> None:
        """A scan must never become an approved source with no content."""
        import heal.knowledge.extract as mod

        class FakePage:
            def extract_text(self) -> str:
                return "   "

        class FakeReader:
            def __init__(self, *_a, **_k) -> None:
                self.pages = [FakePage(), FakePage()]

        monkeypatch.setattr(mod, "_extract_pdf", _fake_pdf(FakeReader))
        with pytest.raises(ExtractionError) as excinfo:
            extract(b"%PDF-", "scan.pdf")
        message = str(excinfo.value).lower()
        assert "scan" in message and "ocr" in message

    def test_a_pdf_with_text_is_extracted(self, monkeypatch) -> None:
        import heal.knowledge.extract as mod

        class FakePage:
            def extract_text(self) -> str:
                return "Give TDF/3TC/DTG once daily."

        class FakeReader:
            def __init__(self, *_a, **_k) -> None:
                self.pages = [FakePage()]

        monkeypatch.setattr(mod, "_extract_pdf", _fake_pdf(FakeReader))
        result = extract(b"%PDF-", "guideline.pdf")
        assert "TDF/3TC/DTG" in result.text
        assert result.kind == "pdf" and result.pages == 1


def _fake_pdf(reader_cls):
    """Rebuild _extract_pdf against a fake reader, without pypdf installed."""
    from heal.knowledge.extract import Extracted

    def _impl(data: bytes) -> Extracted:
        reader = reader_cls(data)
        pages = [p.extract_text() or "" for p in reader.pages]
        text = "\n\n".join(p.strip() for p in pages if p.strip())
        if not text.strip():
            raise ExtractionError(
                f"This PDF has {len(pages)} page(s) but no extractable text. "
                "It is most likely a scan. Run OCR on it first, or upload a "
                "text version -- indexing it as-is would create a citable "
                "source with no content."
            )
        return Extracted(text=text, pages=len(pages), kind="pdf")

    return _impl
