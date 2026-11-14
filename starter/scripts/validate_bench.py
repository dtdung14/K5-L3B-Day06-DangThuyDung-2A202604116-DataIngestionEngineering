import json, re, unicodedata
from collections import Counter

def norm(t):
    t = unicodedata.normalize("NFC", t or "").replace("\u00a0", " ").replace("\u00ad", "")
    return re.sub(r"\s+", "", t).casefold()

pages = {}
for l in open("outputs/pages.jsonl", encoding="utf-8"):
    r = json.loads(l); pages[r["page"]] = r
bench = json.load(open("benchmark/benchmark.json", encoding="utf-8"))

bad = 0
for q in bench:
    p = pages.get(q["gold_page"])
    ok = p is not None and norm(q["evidence_quote"]) in norm(p["text"])
    sec_ok = True
    if q.get("filter"):
        sec_ok = p is not None and p["metadata"]["section"] == q["filter"]["section"]
    if not ok or not sec_ok:
        bad += 1
        print("LỖI", q["id"], "page", q["gold_page"], "| quote_ok:", ok, "| filter_khớp_gold:", sec_ok)

c = Counter(q["split"] for q in bench)
f = Counter(q["split"] for q in bench if q.get("filter"))
print(f"Tổng {len(bench)} | dev {c['dev']} | test {c['test']} | filter dev {f['dev']} | filter test {f['test']}")
print("TẤT CẢ OK" if bad == 0 else f"{bad} câu lỗi")