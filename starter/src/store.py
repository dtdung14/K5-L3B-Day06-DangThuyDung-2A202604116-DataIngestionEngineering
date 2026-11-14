"TODO""Store and search vectors using PostgreSQL + pgvector (cosine, exact search)."""
import json
from typing import Any

import numpy as np
import psycopg
from pgvector.psycopg import register_vector
from psycopg import sql

from .models import Chunk

# Chiến lược -> bảng. C dùng chung bảng với B; chỉ khác ở filter lúc search.
TABLES = {"A": "chunks_a", "B": "chunks_b", "C": "chunks_b"}
# Cột được phép lọc (tên cột không thể tham số hóa, nên dùng whitelist).
ALLOWED_FILTERS = {"section", "document_id"}


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int) -> None:
        if not database_url:
            raise ValueError("Thiếu DATABASE_URL")
        if dimensions <= 0:
            raise ValueError(f"dimensions không hợp lệ: {dimensions}")
        self.database_url = database_url
        self.dimensions = dimensions

    def _connect(self) -> psycopg.Connection:
        try:
            conn = psycopg.connect(self.database_url, connect_timeout=10)
        except Exception as e:  # báo lỗi rõ, không fallback
            raise RuntimeError(f"Không kết nối được PostgreSQL: {e}") from e
        register_vector(conn)
        return conn

    @staticmethod
    def _table(strategy: str) -> sql.Identifier:
        if strategy not in TABLES:
            raise ValueError(f"Chiến lược không hợp lệ: {strategy!r} (chỉ {list(TABLES)})")
        return sql.Identifier(TABLES[strategy])

    def create_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            register_vector(conn)
            for name in sorted(set(TABLES.values())):
                t = sql.Identifier(name)
                conn.execute(sql.SQL("""
                    CREATE TABLE IF NOT EXISTS {t} (
                        chunk_id    TEXT PRIMARY KEY,
                        document_id TEXT NOT NULL,
                        source      TEXT NOT NULL,
                        page        INT  NOT NULL,
                        section     TEXT,
                        text        TEXT NOT NULL,
                        metadata    JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                        embedding   vector({dim}) NOT NULL
                    )""").format(t=t, dim=sql.Literal(self.dimensions)))
                conn.execute(sql.SQL("CREATE INDEX IF NOT EXISTS {i} ON {t} (section)").format(
                    i=sql.Identifier(f"idx_{name}_section"), t=t))
                row = conn.execute(
                    "SELECT atttypmod FROM pg_attribute "
                    "WHERE attrelid = %s::regclass AND attname = 'embedding'", (name,)
                ).fetchone()
                if row and row[0] != self.dimensions:
                    raise RuntimeError(
                        f"Bảng {name} có vector({row[0]}) nhưng model là {self.dimensions} chiều. "
                        "Xóa bảng hoặc dùng lại đúng model.")

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """Ghi theo chunk_id (idempotent). Xóa chunk cũ của các document_id đang nạp
        mà không còn trong lần nạp này. Giả định mỗi lần nạp là TOÀN BỘ document."""
        if len(chunks) != len(vectors):
            raise ValueError(f"{len(chunks)} chunk nhưng {len(vectors)} vector")
        if not chunks:
            raise ValueError("Không có chunk để nạp")
        for c, v in zip(chunks, vectors):
            if len(v) != self.dimensions:
                raise ValueError(f"Vector của {c.chunk_id} có {len(v)} chiều, cần {self.dimensions}")

        t = self._table(strategy)
        rows = [
            (c.chunk_id, c.document_id, c.source, c.page,
             c.metadata.get("section"), c.text,
             json.dumps(c.metadata, ensure_ascii=False),
             np.asarray(v, dtype=np.float32))
            for c, v in zip(chunks, vectors)
        ]
        doc_ids = sorted({c.document_id for c in chunks})
        new_ids = [c.chunk_id for c in chunks]

        with self._connect() as conn:  # một transaction: lỗi thì rollback toàn bộ
            conn.execute(sql.SQL(
                "DELETE FROM {t} WHERE document_id = ANY(%s) AND chunk_id <> ALL(%s)"
            ).format(t=t), (doc_ids, new_ids))
            with conn.cursor() as cur:
                cur.executemany(sql.SQL("""
                    INSERT INTO {t} (chunk_id, document_id, source, page, section, text, metadata, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        document_id = EXCLUDED.document_id, source = EXCLUDED.source,
                        page = EXCLUDED.page, section = EXCLUDED.section, text = EXCLUDED.text,
                        metadata = EXCLUDED.metadata, embedding = EXCLUDED.embedding
                """).format(t=t), rows)

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if len(query_vector) != self.dimensions:
            raise ValueError(f"Query có {len(query_vector)} chiều, cần {self.dimensions}")
        t = self._table(strategy)
        q = np.asarray(query_vector, dtype=np.float32)

        conds, params = [], []
        for key, value in (filters or {}).items():
            if key not in ALLOWED_FILTERS:   # không bỏ qua im lặng
                raise ValueError(f"Filter không được phép: {key!r} (cho phép {sorted(ALLOWED_FILTERS)})")
            conds.append(sql.SQL("{c} = %s").format(c=sql.Identifier(key)))
            params.append(value)
        where = sql.SQL(" WHERE ") + sql.SQL(" AND ").join(conds) if conds else sql.SQL("")

        query = sql.SQL("""
            SELECT chunk_id, document_id, source, page, section, text, metadata,
                   1 - (embedding <=> %s) AS score
            FROM {t}{where}
            ORDER BY embedding <=> %s
            LIMIT %s
        """).format(t=t, where=where)

        with self._connect() as conn:
            rows = conn.execute(query, [q, *params, q, top_k]).fetchall()
        return [
            {"chunk_id": r[0], "document_id": r[1], "source": r[2], "page": r[3],
             "section": r[4], "text": r[5], "metadata": r[6], "score": float(r[7])}
            for r in rows
        ]

    # --- hàm phụ ---
    def count(self, strategy: str) -> int:
        with self._connect() as conn:
            return conn.execute(sql.SQL("SELECT count(*) FROM {t}").format(
                t=self._table(strategy))).fetchone()[0]

    def delete_document(self, strategy: str, document_id: str) -> int:
        """Xóa mọi chunk của một tài liệu (dùng khi tài liệu đổi hoặc dọn test)."""
        with self._connect() as conn:
            cur = conn.execute(sql.SQL("DELETE FROM {t} WHERE document_id = %s").format(
                t=self._table(strategy)), (document_id,))
            return cur.rowcount