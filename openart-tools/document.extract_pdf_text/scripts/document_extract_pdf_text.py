from __future__ import annotations

import argparse
import re
from pathlib import Path
import subprocess
import tempfile
import zlib


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_pdf")
    parser.add_argument("output_text", nargs="?")
    return parser.parse_args()


def _decode_pdf_string(data: bytes) -> str:
    out = bytearray()
    i = 0
    mapping = {
        ord("n"): b"\n",
        ord("r"): b"\r",
        ord("t"): b"\t",
        ord("b"): b"\b",
        ord("f"): b"\f",
        ord("("): b"(",
        ord(")"): b")",
        ord("\\"): b"\\",
    }
    while i < len(data):
        b = data[i]
        if b == 0x5C:
            i += 1
            if i >= len(data):
                break
            c = data[i]
            if c in mapping:
                out.extend(mapping[c])
            elif 48 <= c <= 55:
                octal = bytes([c])
                for _ in range(2):
                    if i + 1 < len(data) and 48 <= data[i + 1] <= 55:
                        i += 1
                        octal += bytes([data[i]])
                    else:
                        break
                value = int(octal, 8)
                if 0 <= value <= 255:
                    out.append(value)
                else:
                    out.extend(octal)
            else:
                out.append(c)
        else:
            out.append(b)
        i += 1
    return out.decode("latin1", errors="replace")


def _extract_strings_from_stream(stream: bytes) -> list[str]:
    texts: list[str] = []
    i = 0
    while i < len(stream):
        if stream[i] == 0x28:
            depth = 1
            i += 1
            buf = bytearray()
            while i < len(stream) and depth > 0:
                b = stream[i]
                if b == 0x5C and i + 1 < len(stream):
                    buf.append(b)
                    i += 1
                    buf.append(stream[i])
                elif b == 0x28:
                    depth += 1
                    buf.append(b)
                elif b == 0x29:
                    depth -= 1
                    if depth > 0:
                        buf.append(b)
                else:
                    buf.append(b)
                i += 1
            texts.append(_decode_pdf_string(bytes(buf)))
        else:
            i += 1
    return texts


def _extract_with_pdfminer(path: Path) -> str:
    from pdfminer.high_level import extract_text  # type: ignore

    return extract_text(str(path))


def _extract_with_pypdf(path: Path) -> str:
    from pypdf import PdfReader  # type: ignore

    reader = PdfReader(str(path))
    texts = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text:
            texts.append(page_text)
    return "\n".join(texts)


def _extract_with_pdftotext(path: Path) -> str:
    proc = subprocess.run(["pdftotext", str(path), "-"], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return ""
    return proc.stdout


def _extract_with_ocr(path: Path) -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        prefix = Path(tmpdir) / "page"
        proc = subprocess.run(["pdftoppm", str(path), str(prefix), "-png", "-r", "300"], capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            return ""
        texts: list[str] = []
        for image_path in sorted(Path(tmpdir).glob("page-*.png")):
            ocr = subprocess.run(["tesseract", str(image_path), "stdout"], capture_output=True, text=True, check=False)
            if ocr.returncode == 0 and ocr.stdout.strip():
                texts.append(ocr.stdout)
        return "\n".join(texts)


def _extract_with_fallback(path: Path) -> str:
    data = path.read_bytes()
    texts: list[str] = []
    for match in re.finditer(rb"stream\r?\n", data):
        start = match.end()
        end = data.find(b"endstream", start)
        if end == -1:
            continue
        blob = data[start:end].rstrip(b"\r\n")
        try:
            decoded = zlib.decompress(blob)
        except Exception:
            continue
        if b"BT" not in decoded and b"Tj" not in decoded and b"TJ" not in decoded:
            continue
        texts.extend(_extract_strings_from_stream(decoded))
    cleaned = []
    for text in texts:
        text = text.strip()
        if not text:
            continue
        cleaned.append(text)
    return "\n".join(cleaned)


def _looks_like_text(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False

    sample = stripped[:20000]
    if not sample:
        return False

    allowed_ascii = set("\n\r\t")
    allowed_ascii.update(chr(i) for i in range(32, 127))
    allowed = sum(1 for ch in sample if ch in allowed_ascii or ch.isalpha())
    lines = sample.splitlines() or [sample]
    max_line_length = max(len(line) for line in lines)
    word_count = len(re.findall(r"[A-Za-z]{2,}", sample))

    if allowed / len(sample) < 0.85:
        return False
    if max_line_length > 1000:
        return False
    if word_count < 5:
        return False
    return True


def extract_pdf_text(path: Path) -> str:
    extractors = [
        _extract_with_pdfminer,
        _extract_with_pypdf,
        _extract_with_pdftotext,
        _extract_with_ocr,
        _extract_with_fallback,
    ]
    for extractor in extractors:
        try:
            text = extractor(path)
        except Exception:
            continue
        if text and _looks_like_text(text):
            return text
    return ""


def main() -> None:
    args = parse_args()
    input_path = Path(args.input_pdf)
    text = extract_pdf_text(input_path)
    if args.output_text:
        output_path = Path(args.output_text)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
