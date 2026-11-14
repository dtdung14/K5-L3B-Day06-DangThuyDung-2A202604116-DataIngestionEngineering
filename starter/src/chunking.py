"""Implement fixed-size and structure-aware chunking."""
from .models import Chunk, DocumentPage
import hashlib
import re

def _chunk_id(page: DocumentPage, strategy: str, index: int, text: str) -> str:
    """ID xác định: nạp lại cùng dữ liệu cho cùng ID => upsert không nhân đôi."""
    key = f"{page.document_id}|{page.page}|{strategy}|{index}|{text}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]


def _make(page: DocumentPage, strategy: str, index: int, text: str, **extra) -> Chunk:
    meta = dict(page.metadata)           # giữ section, ...
    meta.update({"strategy": strategy, "chunk_index": index, **extra})
    return Chunk(
        chunk_id=_chunk_id(page, strategy, index, text),
        document_id=page.document_id,
        source=page.source,
        page=page.page,
        text=text,
        metadata=meta,
    )

def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    """TODO: split text into overlapping windows and retain page metadata."""
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError(f"Tham số không hợp lệ: size={size}, overlap={overlap}")
    text = page.text
    step = size - overlap
    chunks: list[Chunk] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        piece = text[start:end].strip()
        if piece:
            chunks.append(_make(page, "fixed", len(chunks), piece, char_start=start, char_end=end))
        if end >= len(text):
            break
        start += step
    return chunks


def _split_long(paragraph: str, max_size: int) -> list[str]:
    """Tách đoạn quá dài: ưu tiên theo câu, câu quá dài thì cắt theo từ."""
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    parts, cur = [], ""
    for s in sentences:
        while len(s) > max_size:                     # câu dài hơn giới hạn: cắt theo từ
            if cur:
                parts.append(cur); cur = ""
            cut = s.rfind(" ", 0, max_size)
            cut = cut if cut > 0 else max_size
            parts.append(s[:cut].strip())
            s = s[cut:].strip()
        if not s:
            continue
        if cur and len(cur) + 1 + len(s) > max_size:
            parts.append(cur); cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        parts.append(cur)
    return parts


def by_paragraph(page: DocumentPage, max_size: int) -> list[Chunk]:
    """TODO: group paragraphs, split oversized paragraphs and retain metadata."""
    if max_size <= 0:
        raise ValueError("max_size phải > 0")
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", page.text) if p.strip()]
    units: list[str] = []
    for p in paragraphs:
        units.extend(_split_long(p, max_size) if len(p) > max_size else [p])

    chunks: list[Chunk] = []
    cur = ""
    for u in units:
        if cur and len(cur) + 2 + len(u) > max_size:
            chunks.append(_make(page, "paragraph", len(chunks), cur))
            cur = u
        else:
            cur = f"{cur}\n\n{u}" if cur else u
    if cur:
        chunks.append(_make(page, "paragraph", len(chunks), cur))
    return chunks
