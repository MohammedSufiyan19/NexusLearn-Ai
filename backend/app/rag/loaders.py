"""
NexusLearn AI — Document Loaders
Loads PDF, DOCX, PPTX with page-level metadata.
Validates magic bytes before processing (Phase 7 upload safety).
"""
import logging
import os

import docx
import pypdf
from langchain_core.documents import Document
from pptx import Presentation

logger = logging.getLogger(__name__)

# ── Magic Byte Validation ─────────────────────────────────────────────────────
# Allowlist by content, not extension

_MAGIC = {
    b"%PDF": "pdf",
    b"PK\x03\x04": "zip",   # DOCX and PPTX are ZIP files
}


def _detect_type(file_path: str) -> str:
    """Read first 4 bytes and return detected type. Raises ValueError if unknown."""
    with open(file_path, "rb") as f:
        header = f.read(4)
    for magic, ftype in _MAGIC.items():
        if header.startswith(magic):
            return ftype
    raise ValueError(f"File header does not match any allowed type. Got: {header!r}")


def _validate_zip_safety(file_path: str, max_uncompressed_mb: int = 200, max_entries: int = 1000):
    """Guard against zip bombs in DOCX/PPTX files."""
    import zipfile
    with zipfile.ZipFile(file_path) as zf:
        entries = zf.infolist()
        if len(entries) > max_entries:
            raise ValueError(f"ZIP contains {len(entries)} entries — possible zip bomb")
        total = sum(e.file_size for e in entries)
        if total > max_uncompressed_mb * 1024 * 1024:
            raise ValueError(
                f"Uncompressed size {total / 1e6:.1f} MB exceeds {max_uncompressed_mb} MB limit"
            )


# ── Loaders ───────────────────────────────────────────────────────────────────

class PDFLoader:
    def __init__(self, file_path: str, filename: str):
        self.file_path = file_path
        self.filename = filename

    def load(self) -> list[Document]:
        docs = []
        try:
            reader = pypdf.PdfReader(self.file_path)
        except Exception as e:
            raise ValueError(f"Could not read PDF: {e}")

        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            text = text.strip()
            if not text:
                continue
            docs.append(Document(
                page_content=text,
                metadata={
                    "source": self.filename,
                    "page": i + 1,
                    "source_type": "pdf",
                }
            ))
        return docs


class DOCXLoader:
    def __init__(self, file_path: str, filename: str):
        self.file_path = file_path
        self.filename = filename

    def load(self) -> list[Document]:
        _validate_zip_safety(self.file_path)
        try:
            doc = docx.Document(self.file_path)
        except Exception as e:
            raise ValueError(f"Could not read DOCX: {e}")

        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        tables = []
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join(c.text.strip() for c in row.cells if c.text.strip())
                if row_text:
                    tables.append(row_text)

        full_text = "\n".join(paragraphs + tables)
        if not full_text:
            return []

        return [Document(
            page_content=full_text,
            metadata={"source": self.filename, "page": 1, "source_type": "docx"}
        )]


class PPTXLoader:
    def __init__(self, file_path: str, filename: str):
        self.file_path = file_path
        self.filename = filename

    def load(self) -> list[Document]:
        _validate_zip_safety(self.file_path)
        try:
            prs = Presentation(self.file_path)
        except Exception as e:
            raise ValueError(f"Could not read PPTX: {e}")

        docs = []
        for i, slide in enumerate(prs.slides):
            texts = [
                shape.text.strip()
                for shape in slide.shapes
                if hasattr(shape, "text") and shape.text.strip()
            ]
            if texts:
                docs.append(Document(
                    page_content="\n".join(texts),
                    metadata={"source": self.filename, "page": i + 1, "source_type": "pptx"}
                ))
        return docs


def load_document(file_path: str, filename: str) -> list[Document]:
    """
    Validates magic bytes then delegates to the correct loader.
    Raises ValueError on unsupported or malformed files.
    """
    ext = os.path.splitext(filename)[1].lower()
    detected = _detect_type(file_path)

    # Cross-check extension vs magic bytes
    if ext == ".pdf" and detected != "pdf":
        raise ValueError("File extension is .pdf but content is not a PDF")
    if ext in (".docx", ".pptx") and detected != "zip":
        raise ValueError(f"File extension is {ext} but content is not a ZIP (Office format)")
    if ext not in (".pdf", ".docx", ".pptx"):
        raise ValueError(f"Unsupported extension: {ext}. Allowed: .pdf .docx .pptx")

    if ext == ".pdf":
        return PDFLoader(file_path, filename).load()
    elif ext == ".docx":
        return DOCXLoader(file_path, filename).load()
    elif ext == ".pptx":
        return PPTXLoader(file_path, filename).load()
