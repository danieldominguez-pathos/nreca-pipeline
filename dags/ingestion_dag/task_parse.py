"""Document parsing task utilities."""

from __future__ import annotations


def parse_document(content_b64: str, filename: str) -> dict:
    """Parse document and extract text content.

    Supports PDF, DOCX, DOC (via antiword), and plain text files.

    Args:
        content_b64: Base64-encoded file content
        filename: Original filename (used to determine file type)

    Returns:
        Dict with parsed content:
        - text: extracted text content
        - filename: original filename
        - page_count: number of pages (1 for non-paginated)
        - file_type: detected file type

    Raises:
        ValueError: If file type is not supported
    """
    import base64

    content = base64.b64decode(content_b64)
    file_lower = filename.lower()

    if file_lower.endswith(".pdf"):
        return _parse_pdf(content, filename)
    elif file_lower.endswith(".docx"):
        return _parse_docx(content, filename)
    elif file_lower.endswith(".doc"):
        return _parse_doc(content, filename)
    elif file_lower.endswith((".txt", ".md", ".csv")):
        return _parse_text(content, filename)
    else:
        raise ValueError(f"Unsupported file type: {filename}")


def _parse_pdf(content: bytes, filename: str) -> dict:
    """Parse PDF document."""
    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    text_parts = []

    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text_parts.append(page_text)

    return {
        "text": "\n\n".join(text_parts),
        "filename": filename,
        "page_count": len(reader.pages),
        "file_type": "pdf",
    }


def _parse_docx(content: bytes, filename: str) -> dict:
    """Parse DOCX document."""
    import io

    from docx import Document

    doc = Document(io.BytesIO(content))
    text_parts = []

    for para in doc.paragraphs:
        if para.text.strip():
            text_parts.append(para.text)

    return {
        "text": "\n\n".join(text_parts),
        "filename": filename,
        "page_count": 1,  # DOCX doesn't have pages
        "file_type": "docx",
    }


def _parse_doc(content: bytes, filename: str) -> dict:
    """Parse legacy .doc document using antiword."""
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".doc", delete=True) as tmp:
        tmp.write(content)
        tmp.flush()

        result = subprocess.run(
            ["antiword", tmp.name],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            raise ValueError(f"antiword failed for {filename}: {result.stderr}")

        text = result.stdout.strip()

    return {
        "text": text,
        "filename": filename,
        "page_count": 1,
        "file_type": "doc",
    }


def _parse_text(content: bytes, filename: str) -> dict:
    """Parse plain text document."""
    # Try common encodings
    for encoding in ["utf-8", "latin-1", "cp1252"]:
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = content.decode("utf-8", errors="replace")

    file_ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"

    return {
        "text": text,
        "filename": filename,
        "page_count": 1,
        "file_type": file_ext,
    }
