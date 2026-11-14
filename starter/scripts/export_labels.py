import csv, json, os, random, re, sys
from pathlib import Path

sys.path.insert(0, os.getcwd())          # chạy từ starter\ để import được src
from src.ingestion import build_chunks, load_pages

CFG = {"fixed_size": 500, "fixed_overlap": 50, "paragraph_max": 800}  # phải giống run.py
SEED = 42
OUT = Path("results/labels")
OUT.mkdir(parents=True, exist_ok=True)
rng = random.Random(SEED)


def write(name, rows, fields):
    with open(OUT / name, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


key_rows = []

# ---------- 1. COHERENCE: 10 vị trí cố định, A vs B (C dùng chunk của B) ----------
# Quy tắc chốt trước: 10 trang PDF đầu (đã sắp xếp); vị trí = đoạn nằm giữa trang.
allp = load_pages()
first10 = sorted(allp, key=lambda p: p.page)[:10]
pair = ["X", "Y"]
rng.shuffle(pair)
cmap = {"A": pair[0], "B": pair[1]}
key_rows += [{"file": "coherence.csv", "code": v, "strategy": k} for k, v in cmap.items()]

coh = []
for p in first10:
    paras = [x for x in re.split(r"\n\s*\n", p.text) if x.strip()]
    para = paras[len(paras) // 2]
    off = p.text.find(para)
    probe = para[:60]
    chunk_a = next((c for c in build_chunks([p], "A", CFG)
                    if c.metadata["char_start"] <= off < c.metadata["char_end"]), None)
    chunk_b = next((c for c in build_chunks([p], "B", CFG) if probe in c.text), None)
    for strat, ch in (("A", chunk_a), ("B", chunk_b)):
        coh.append({
            "position_id": f"p{p.page}", "pdf_page": p.page, "code": cmap[strat],
            "position_start_text": probe,
            "chunk_text": ch.text if ch else "KHONG TIM THAY CHUNK",
            "coherence_0_1_2": "", "reason": "",
        })
rng.shuffle(coh)
write("coherence.csv", coh,
      ["position_id", "pdf_page", "code", "position_start_text", "chunk_text", "coherence_0_1_2", "reason"])

# ---------- 2. METADATA + GROUNDING: 5 câu test x top-3 ----------
traces = json.load(open("outputs/traces/traces_test.json", encoding="utf-8"))
bench = {q["id"]: q for q in json.load(open("benchmark/benchmark.json", encoding="utf-8"))}
codes = ["S1", "S2", "S3"]
rng.shuffle(codes)
smap = dict(zip(["A", "B", "C"], codes))
key_rows += [{"file": "metadata.csv / grounding.csv", "code": v, "strategy": k} for k, v in smap.items()]

meta_rows, ground_rows, filt_rows = [], [], []
for t in sorted(traces, key=lambda x: (x["question_id"], smap[x["strategy"]])):
    q = bench[t["question_id"]]
    code = smap[t["strategy"]]
    joined = "\n\n".join(f"[hang {h['rank']} | trang {h['page']}] {h['text']}" for h in t["top3"])
    ground_rows.append({
        "question_id": q["id"], "code": code, "question": q["question"],
        "expected_answer": q["expected_answer"], "gold_evidence": q["evidence_quote"],
        "top3_text": joined, "grounding_0_1_2": "", "reason": "",
    })
    for h in t["top3"]:
        meta_rows.append({
            "question_id": q["id"], "code": code, "rank": h["rank"],
            "source": h["source"], "page": h["page"], "section": h["section"],
            "chunk_start": h["text"][:200].replace("\n", " "),
            "metadata_ok_1_0": "", "error_note": "",
        })
    if q.get("filter"):
        want = q["filter"]["section"]
        filt_rows.append({
            "question_id": q["id"], "strategy": t["strategy"], "filter_section": want,
            "all_top3_match": all(h["section"] == want for h in t["top3"]),
            "note": "filter da ap dung" if t["strategy"] == "C" else "thong tin tham khao (A/B khong loc) -> bao N/A",
        })

write("grounding.csv", ground_rows,
      ["question_id", "code", "question", "expected_answer", "gold_evidence", "top3_text", "grounding_0_1_2", "reason"])
write("metadata.csv", meta_rows,
      ["question_id", "code", "rank", "source", "page", "section", "chunk_start", "metadata_ok_1_0", "error_note"])
write("filter_compliance.csv", filt_rows,
      ["question_id", "strategy", "filter_section", "all_top3_match", "note"])
write("label_key_DO_NOT_OPEN.csv", key_rows, ["file", "code", "strategy"])

print(f"coherence: {len(coh)} dong | grounding: {len(ground_rows)} | metadata: {len(meta_rows)} | filter: {len(filt_rows)}")
print("Da ghi vao", OUT.resolve())