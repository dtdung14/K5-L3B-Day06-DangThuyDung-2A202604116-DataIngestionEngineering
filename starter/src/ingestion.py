"""Read and normalize source data; build chunks per strategy, embed, store, measure."""
import json
import re
import statistics
import time
import unicodedata
from pathlib import Path

import fitz  # PyMuPDF

from .chunking import by_paragraph, fixed_size
from .models import Chunk, DocumentPage


def normalize_text(text: str) -> str:
    """NFC, bỏ nbsp/soft hyphen, gộp khoảng trắng trong đoạn.
    Giữ ranh giới đoạn (dòng trống) vì by_paragraph cần cấu trúc này."""
    t = unicodedata.normalize("NFC", text or "")
    t = t.replace("\u00a0", " ").replace("\u00ad", "")
    paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", t)]
    return "\n\n".join(p for p in paras if p)


def load_pdf(path: Path, document_id: str, source: str) -> list[DocumentPage]:
    """Trích mọi trang vật lý (page = số trang PDF, từ 1).
    Trang rỗng hoặc lỗi đọc vẫn được trả về, kèm cờ trong metadata."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Không thấy file PDF: {path}")
    pages: list[DocumentPage] = []
    with fitz.open(path) as doc:
        for i, page in enumerate(doc, start=1):
            meta: dict = {}
            try:
                blocks = [b[4] for b in page.get_text("blocks", sort=True) if b[6] == 0]
                text = normalize_text("\n\n".join(blocks))
            except Exception as e:
                text, meta["error"] = "", str(e)
            meta["n_chars"] = len(text)
            meta["empty"] = len(text) == 0
            pages.append(DocumentPage(document_id, source, i, text, meta))
    return pages


# ---------- phần pipeline (run.py dùng) ----------

def load_pages(path: str = "outputs/pages.jsonl") -> list[DocumentPage]:
    pages = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            pages.append(DocumentPage(r["document_id"], r["source"], r["page"], r["text"], r["metadata"]))
    if len(pages) < 30:
        raise RuntimeError(f"Chỉ có {len(pages)} trang, cần >= 30 trang nội dung")
    return pages


def build_chunks(pages: list[DocumentPage], strategy: str, cfg: dict) -> list[Chunk]:
    chunks: list[Chunk] = []
    for p in pages:
        if strategy == "A":
            chunks.extend(fixed_size(p, cfg["fixed_size"], cfg["fixed_overlap"]))
        elif strategy == "B":
            chunks.extend(by_paragraph(p, cfg["paragraph_max"]))
        else:
            raise ValueError("Chỉ ingest A hoặc B (C dùng chung bảng B)")
    return chunks


def chunk_stats(chunks: list[Chunk]) -> dict:
    lens = [len(c.text) for c in chunks]
    return {"n_chunks": len(chunks), "total_chars": sum(lens), "min_len": min(lens),
            "mean_len": round(statistics.mean(lens), 1), "median_len": statistics.median(lens),
            "max_len": max(lens)}


def ingest(strategy: str, pages, embedder, store, cfg: dict) -> dict:
    t0 = time.perf_counter()
    chunks = build_chunks(pages, strategy, cfg)
    vectors = embedder.embed_documents([c.text for c in chunks])
    store.upsert(strategy, chunks, vectors)
    stats = chunk_stats(chunks)
    stats.update({"strategy": strategy, "ingest_seconds": round(time.perf_counter() - t0, 2),
                  "cost_usd": 0.0, "rows_in_db": store.count(strategy)})
    Path("outputs").mkdir(exist_ok=True)
    with open(f"outputs/ingest_stats_{strategy}.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    return stats