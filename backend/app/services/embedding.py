from typing import List
import numpy as np
import os
import threading

from ..config import settings


class EmbeddingService:
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._model = None
        self._reranker = None
        self._dimension = settings.EMBEDDING_DIM

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(settings.EMBEDDING_MODEL)
            self._dimension = self._model.get_sentence_embedding_dimension()

    def _load_reranker(self):
        if self._reranker is None:
            try:
                from sentence_transformers import CrossEncoder
                self._reranker = CrossEncoder(settings.RERANKER_MODEL)
            except Exception:
                self._reranker = None

    @property
    def dimension(self) -> int:
        self._load_model()
        return self._dimension

    def encode(self, texts: List[str], batch_size: int = 32, normalize: bool = True) -> np.ndarray:
        self._load_model()
        if not texts:
            return np.zeros((0, self._dimension), dtype=np.float32)
        embeddings = self._model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=normalize
        )
        return embeddings.astype(np.float32)

    def encode_single(self, text: str, normalize: bool = True) -> np.ndarray:
        vec = self.encode([text], batch_size=1, normalize=normalize)
        return vec[0] if len(vec) > 0 else np.zeros(self._dimension, dtype=np.float32)

    def rerank(self, query: str, passages: List[str]) -> np.ndarray:
        self._load_reranker()
        if self._reranker is None or not passages:
            return np.ones(len(passages), dtype=np.float32)
        pairs = [[query, p] for p in passages]
        scores = self._reranker.predict(pairs, convert_to_numpy=True)
        return scores.astype(np.float32)


def get_embedding_service() -> EmbeddingService:
    return EmbeddingService.get_instance()
