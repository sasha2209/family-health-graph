"""Turn an uploaded document into text, locally and for free.

Order of preference, cheapest first:
1. PDFs that already contain text (most lab portals and hospital systems export these): read the text layer.
2. Photos and scanned PDFs: Tesseract OCR on this server.

Nothing here calls an external service. If Tesseract isn't installed, images come back
with no text and the pipeline decides whether the AI reader may look at the image.
"""
from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

MAX_PAGES = 10
SUPPORTED = {"application/pdf", "image/jpeg", "image/png", "image/webp", "image/tiff"}


class UnsupportedDocument(ValueError):
    pass


@dataclass
class TextResult:
    text: str
    method: str  # "pdf_text" | "ocr" | "none"
    pages: int = 1
    confidence: Optional[float] = None  # mean OCR word confidence 0-100; None for text PDFs
    images: list[bytes] = field(default_factory=list)  # page images (PNG), for an AI fallback


def sniff(data: bytes) -> str:
    """Media type from the file's first bytes; the client-declared type isn't trusted."""
    if data.startswith(b"%PDF"):
        return "application/pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    if data[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftyphevc"):
        raise UnsupportedDocument("HEIC photos aren't supported yet. Choose JPEG in your camera settings, or take the photo in the app.")
    raise UnsupportedDocument("Upload a PDF or a photo (JPEG or PNG).")


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def _prepare(image_bytes: bytes) -> bytes:
    """Straighten, grayscale and enlarge small photos: cheap steps that noticeably help Tesseract."""
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(image_bytes)) as im:
        im = ImageOps.exif_transpose(im).convert("L")
        longest = max(im.size)
        if longest < 1600:
            scale = 1600 / longest
            im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
        elif longest > 4000:
            im.thumbnail((4000, 4000))
        im = ImageOps.autocontrast(im, cutoff=1)
        out = io.BytesIO()
        im.save(out, "PNG")
        return out.getvalue()


def _tesseract(png: bytes) -> tuple[str, Optional[float]]:
    """Run Tesseract, returning text rebuilt line by line and the mean word confidence."""
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "page.png"
        src.write_bytes(png)
        proc = subprocess.run(["tesseract", str(src), "stdout", "-l", "eng", "--psm", "4", "tsv"],
                              capture_output=True, timeout=90, check=False)
    if proc.returncode != 0:
        return "", None
    lines: dict[tuple, list[str]] = {}
    confs: list[float] = []
    for row in proc.stdout.decode("utf-8", "replace").splitlines()[1:]:
        cols = row.split("\t")
        if len(cols) < 12 or not cols[11].strip():
            continue
        try:
            conf = float(cols[10])
        except ValueError:
            continue
        if conf >= 0:
            confs.append(conf)
        lines.setdefault((int(cols[2]), int(cols[3]), int(cols[4])), []).append(cols[11])
    text = "\n".join(" ".join(words) for _, words in sorted(lines.items()))
    return text, (sum(confs) / len(confs) if confs else None)


def _ocr_images(pngs: list[bytes]) -> TextResult:
    if not tesseract_available():
        return TextResult("", "none", len(pngs), None, pngs)
    texts, confs = [], []
    for png in pngs:
        text, conf = _tesseract(png)
        texts.append(text)
        if conf is not None:
            confs.append(conf)
    return TextResult("\n\n".join(texts).strip(), "ocr", len(pngs),
                      sum(confs) / len(confs) if confs else None, pngs)


def _pdf_pages_as_png(data: bytes, pages: int) -> list[bytes]:
    if not shutil.which("pdftoppm"):
        return []
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "doc.pdf"
        src.write_bytes(data)
        subprocess.run(["pdftoppm", "-r", "200", "-gray", "-png", "-l", str(pages), str(src), str(Path(tmp) / "p")],
                       capture_output=True, timeout=120, check=False)
        return [p.read_bytes() for p in sorted(Path(tmp).glob("p*.png"))]


def extract_text(data: bytes) -> tuple[str, TextResult]:
    """Return (media type, text result) for an uploaded file."""
    media_type = sniff(data)
    if media_type == "application/pdf":
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError

        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise UnsupportedDocument("This PDF is password-protected. Remove the password and upload it again.")
            pages = reader.pages[:MAX_PAGES]
            text = "\n\n".join((p.extract_text() or "") for p in pages).strip()
        except PdfReadError as exc:
            raise UnsupportedDocument("This PDF couldn't be read.") from exc
        # A real text layer has words on most pages; scans have none (or a stray header).
        if len(text) >= 60 * len(pages):
            return media_type, TextResult(text, "pdf_text", len(pages))
        return media_type, _ocr_images([_prepare(p) for p in _pdf_pages_as_png(data, len(pages))])
    try:
        png = _prepare(data)
    except Exception as exc:  # Pillow raises several types for corrupt files
        raise UnsupportedDocument("This image couldn't be opened.") from exc
    return media_type, _ocr_images([png])
