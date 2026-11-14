"""Local multilingual embedder (Sentence Transformers). No mock fallback."""
from typing import Protocol


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        ...

    def embed_query(self, question: str) -> list[float]:
        """Return a query vector compatible with the stored document vectors."""
        ...


class MyEmbedder:
    """Sentence Transformers adapter. E5 models need 'query: ' / 'passage: ' prefixes."""

    def __init__(self, model_name: str, batch_size: int = 32) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise RuntimeError("Thiếu sentence-transformers: pip install sentence-transformers") from e
        try:
            self._model = SentenceTransformer(model_name)
        except Exception as e:
            raise RuntimeError(f"Không tải được model '{model_name}': {e}") from e
        self.dimensions = int(self._model.get_sentence_embedding_dimension())
        self._is_e5 = "e5" in model_name.lower()

    def _encode(self, texts: list[str]) -> list[list[float]]:
        vecs = self._model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,   # cosine nhất quán cho A/B/C
            show_progress_bar=False,
        )
        return vecs.tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._is_e5:
            texts = [f"passage: {t}" for t in texts]
        return self._encode(texts)

    def embed_query(self, question: str) -> list[float]:
        q = f"query: {question}" if self._is_e5 else question
        return self._encode([q])[0]