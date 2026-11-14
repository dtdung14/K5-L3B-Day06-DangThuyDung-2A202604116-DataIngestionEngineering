"""Pipeline: python -m src.run load | ingest | eval --split dev|test|all"""
import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from .embeddings import MyEmbedder
from .evaluation import evaluate_query, summarize
from .ingestion import ingest, load_pages
from .store import PgVectorStore

load_dotenv()  # đọc starter\.env khi chạy từ starter\

CFG = {"fixed_size": 500, "fixed_overlap": 50, "paragraph_max": 800}
TOP_K = 3


def _setup():
    model = os.environ.get("EMBEDDING_MODEL")
    url = os.environ.get("DATABASE_URL")
    if not model or not url:
        raise SystemExit("Thiếu EMBEDDING_MODEL hoặc DATABASE_URL trong .env")
    emb = MyEmbedder(model)
    store = PgVectorStore(url, emb.dimensions)
    store.create_schema()
    return emb, store


def cmd_ingest() -> None:
    emb, store = _setup()
    pages = load_pages()
    for s in ("A", "B"):
        print(s, ingest(s, pages, emb, store, CFG))


def cmd_eval(split: str) -> None:
    emb, store = _setup()
    questions = json.load(open("benchmark/benchmark.json", encoding="utf-8"))
    if split != "all":
        questions = [q for q in questions if q["split"] == split]
    traces = []
    for strategy in ("A", "B", "C"):
        for q in questions:
            filters = q.get("filter") if strategy == "C" else None  # C chỉ lọc khi câu có filter
            hits = store.search(strategy, emb.embed_query(q["question"]), TOP_K, filters or None)
            t = evaluate_query(q, hits)
            t["strategy"] = strategy
            traces.append(t)
    Path("outputs/traces").mkdir(parents=True, exist_ok=True)
    with open(f"outputs/traces/traces_{split}.json", "w", encoding="utf-8") as f:
        json.dump(traces, f, ensure_ascii=False, indent=2)
    print(json.dumps(summarize(traces), ensure_ascii=False, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["load", "ingest", "eval"])
    ap.add_argument("--split", default="dev", choices=["dev", "test", "all"])
    a = ap.parse_args()
    if a.cmd == "load":
        from .load import main as load_main
        load_main()
    elif a.cmd == "ingest":
        cmd_ingest()
    else:
        cmd_eval(a.split)


if __name__ == "__main__":
    main()