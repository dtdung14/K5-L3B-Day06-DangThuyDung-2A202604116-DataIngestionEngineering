"""TODO: evaluate retrieved evidence and preserve per-query traces."""
from typing import Any
import re
import unicodedata
from collections import defaultdict
from typing import Any


def _norm(text: str) -> str:
    """Chuẩn hóa để so khớp: NFC, casefold, bỏ mọi khoảng trắng.
    Bỏ khoảng trắng để xuống dòng/ngắt từ trong PDF không làm trượt evidence."""
    t = unicodedata.normalize("NFC", text or "")
    t = t.replace("\u00a0", " ").replace("\u00ad", "")
    return re.sub(r"\s+", "", t).casefold()


def _golds(question: dict[str, Any]) -> list[dict[str, Any]]:
    golds = [{
        "gold_source_id": question.get("gold_source_id"),
        "gold_page": question.get("gold_page"),
        "evidence_quote": question.get("evidence_quote", ""),
    }]
    golds.extend(question.get("alt_gold", []) or [])   # bằng chứng thay thế đã ghi
    return golds


def _hit_source_ids(hit: dict[str, Any]) -> set[str]:
    # GIẢ ĐỊNH: khóa nào trong số này khớp gold_source_id cũng được chấp nhận
    return {str(hit[k]) for k in ("source_id", "document_id", "source") if hit.get(k) is not None}


def _check_hit(hit: dict[str, Any], golds: list[dict[str, Any]]) -> dict[str, Any]:
    text = _norm(hit.get("text") or hit.get("content") or "")
    page_match_no_evidence = False
    for g in golds:
        src_ok = str(g["gold_source_id"]) in _hit_source_ids(hit)
        page_ok = hit.get("page") is not None and int(hit["page"]) == int(g["gold_page"])
        if not (src_ok and page_ok):
            continue
        quote = _norm(g.get("evidence_quote", ""))
        if quote and quote in text:
            return {"hit": True, "reason": "source+page+full_evidence", "matched_gold_page": g["gold_page"]}
        page_match_no_evidence = True
    reason = "right_page_but_evidence_incomplete(split_across_chunks?)" if page_match_no_evidence else "wrong_source_or_page"
    return {"hit": False, "reason": reason, "matched_gold_page": None}

def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    """TODO: check source/page and enough gold evidence; keep hit@1 and hit@3 trace.

    Accept any documented alternative gold evidence. Do not infer human grounding
    or chunk coherence labels from exact string match.
    """
    golds = _golds(question)
    top3 = hits[:3]
    checks = [_check_hit(h, golds) for h in top3]
    flags = [c["hit"] for c in checks]
    return {
        "question_id": question.get("id"),
        "split": question.get("split"),
        "question": question.get("question"),
        "filter": question.get("filter"),
        "hit_at_1": bool(flags[0]) if flags else False,
        "hit_at_3": any(flags),
        "top3": [
            {
                "rank": i + 1,
                "chunk_id": h.get("chunk_id"),
                "score": h.get("score"),
                "source": h.get("source_id") or h.get("document_id") or h.get("source"),
                "page": h.get("page"),
                "section": h.get("section"),
                "text": h.get("text") or h.get("content"),
                "hit": c["hit"],
                "reason": c["reason"],
            }
            for i, (h, c) in enumerate(zip(top3, checks))
        ],
        "gold": golds,

    }

def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """TODO: aggregate Hit@1 and Evidence Hit@3 by strategy and dev/test split."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for t in traces:
        groups[(t.get("strategy", "?"), t.get("split", "?"))].append(t)
    out: dict[str, Any] = {}
    for (strategy, split), ts in sorted(groups.items()):
        n = len(ts)
        h1 = sum(t["hit_at_1"] for t in ts)
        h3 = sum(t["hit_at_3"] for t in ts)
        out[f"{strategy}/{split}"] = {
            "n_questions": n,
            "hit_at_1": f"{h1}/{n}",
            "evidence_hit_at_3": f"{h3}/{n}",
            "hit_at_1_rate": round(h1 / n, 3) if n else None,
            "evidence_hit_at_3_rate": round(h3 / n, 3) if n else None,
        }
    return out
