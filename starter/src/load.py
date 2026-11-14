import datetime, json, sys
from pathlib import Path
import yaml
from .ingestion import load_pdf
from .models import DocumentPage


def main(config="configs/corpus.yaml"):
    cfg = yaml.safe_load(open(config, encoding="utf-8"))
    allp = load_pdf(Path(cfg["pdf_path"]), cfg["source_id"], cfg["title"])
    by_no = {p.page: p for p in allp}
    off = cfg["page_offset"]
    excluded = {e["page"]: e["reason"] for e in cfg.get("exclude_pages", [])}
    pages, errors, counted = [], [], []

    for ch in cfg["chapters"]:
        if ch["start"] < 1 or ch["end"] < ch["start"] or ch["end"] > len(allp):
            sys.exit(f"Phạm vi chương không hợp lệ: {ch}")
        for n in range(ch["start"], ch["end"] + 1):
            p = by_no[n]
            if n in excluded:
                errors.append({"page": n, "issue": "excluded", "reason": excluded[n]}); continue
            if p.metadata.get("error"):
                errors.append({"page": n, "issue": "read_error", "reason": p.metadata["error"]}); continue
            if len(p.text) < 200:
                errors.append({"page": n, "issue": "too_short", "reason": f"{len(p.text)} chars"}); continue
            counted.append(n)
            pages.append(DocumentPage(p.document_id, p.source, n, p.text,
                {"section": ch["name"], "printed_page": n - off, "n_chars": len(p.text)}))

    Path("outputs").mkdir(exist_ok=True)
    with open("outputs/pages.jsonl", "w", encoding="utf-8") as f:
        for p in pages:
            f.write(json.dumps({"document_id": p.document_id, "source": p.source, "page": p.page,
                                "text": p.text, "metadata": p.metadata}, ensure_ascii=False) + "\n")
    manifest = {
        "source_id": cfg["source_id"], "title": cfg["title"],
        "source_path_or_url": cfg["source_url"], "license_or_permission": cfg["license_or_permission"],
        "edition_or_version": cfg["edition_or_version"],
        "accessed_at": datetime.date.today().isoformat(),
        "physical_pages_in_pdf": len(allp), "page_offset": off, "chapters": cfg["chapters"],
        "counted_pdf_pages": counted, "n_counted_pages": len(counted),
        "total_chars": sum(p.metadata["n_chars"] for p in pages),
        "counting_rule": "Trang nội dung Chương 1-2 (từ trang mở đầu đến hết mục x.4); loại Key Terms, Summary, câu hỏi cuối chương, trang trống/quá ngắn (xem load_errors.json).",
    }
    json.dump(manifest, open("manifest.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump(errors, open("outputs/load_errors.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"Trang được tính: {len(counted)} | ký tự: {manifest['total_chars']} | lỗi/loại: {len(errors)}")
    if len(counted) < 30:
        print("CẢNH BÁO: chưa đủ 30 trang nội dung.")


if __name__ == "__main__":
    main()