import faiss
import numpy as np
import os
import pickle
import threading
from typing import List, Tuple, Optional, Dict

from ..config import settings


class VectorIndex:
    def __init__(self, knowledge_base_id: str, dimension: int):
        self.kb_id = knowledge_base_id
        self.dimension = dimension
        self._index = None
        self._chunk_ids: List[str] = []
        self._deleted_mask: set = set()
        self._lock = threading.RLock()
        self._use_ivf = False
        self._base_dir = os.path.join(settings.INDEX_DIR, knowledge_base_id)
        os.makedirs(self._base_dir, exist_ok=True)
        self._index_path = os.path.join(self._base_dir, "index.faiss")
        self._meta_path = os.path.join(self._base_dir, "meta.pkl")

    def _create_flat_index(self):
        index = faiss.IndexFlatIP(self.dimension)
        return index

    def _create_ivf_index(self, nlist: int = 100):
        quantizer = faiss.IndexFlatIP(self.dimension)
        index = faiss.IndexIVFFlat(quantizer, self.dimension, nlist, faiss.METRIC_INNER_PRODUCT)
        return index

    def load(self) -> bool:
        with self._lock:
            if not os.path.exists(self._index_path):
                self._index = self._create_flat_index()
                self._chunk_ids = []
                self._deleted_mask = set()
                return False
            try:
                self._index = faiss.read_index(self._index_path)
                if os.path.exists(self._meta_path):
                    with open(self._meta_path, "rb") as f:
                        meta = pickle.load(f)
                        self._chunk_ids = meta.get("chunk_ids", [])
                        self._deleted_mask = set(meta.get("deleted_mask", set()))
                        self._use_ivf = meta.get("use_ivf", False)
                return True
            except Exception:
                self._index = self._create_flat_index()
                self._chunk_ids = []
                self._deleted_mask = set()
                return False

    def save(self):
        with self._lock:
            try:
                faiss.write_index(self._index, self._index_path)
                with open(self._meta_path, "wb") as f:
                    pickle.dump({
                        "chunk_ids": self._chunk_ids,
                        "deleted_mask": list(self._deleted_mask),
                        "use_ivf": self._use_ivf
                    }, f)
            except Exception as e:
                print(f"Failed to save index: {e}")

    def add_vectors(self, vectors: np.ndarray, chunk_ids: List[str]):
        with self._lock:
            if self._index is None:
                self._index = self._create_flat_index()

            if vectors.ndim == 1:
                vectors = vectors.reshape(1, -1)

            total_count = len(self._chunk_ids) + vectors.shape[0]
            should_switch_ivf = total_count > settings.IVF_THRESHOLD and not self._use_ivf

            if should_switch_ivf:
                self._switch_to_ivf()

            self._index.add(vectors)
            self._chunk_ids.extend(chunk_ids)

    def _switch_to_ivf(self):
        try:
            if self._index.ntotal == 0:
                self._index = self._create_ivf_index()
                self._use_ivf = True
                return

            xb = faiss.rev_swig_ptr(self._index.get_xb(), self._index.ntotal * self.dimension)
            xb = np.array(xb).reshape(self._index.ntotal, self.dimension).astype(np.float32)

            nlist = min(100, max(10, xb.shape[0] // 100))
            new_index = self._create_ivf_index(nlist)
            new_index.train(xb)
            new_index.add(xb)
            self._index = new_index
            self._use_ivf = True
        except Exception as e:
            print(f"Failed to switch to IVF: {e}")

    def mark_deleted(self, chunk_ids: List[str]):
        with self._lock:
            for cid in chunk_ids:
                if cid in self._chunk_ids:
                    self._deleted_mask.add(cid)

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int = 20
    ) -> Tuple[List[str], List[float]]:
        with self._lock:
            if self._index is None or self._index.ntotal == 0:
                return [], []

            effective_k = top_k
            if self._deleted_mask:
                effective_k = min(top_k * 3, self._index.ntotal)

            if query_vector.ndim == 1:
                query_vector = query_vector.reshape(1, -1)

            if self._use_ivf and isinstance(self._index, faiss.IndexIVFFlat):
                self._index.nprobe = min(20, self._index.nlist)

            scores, indices = self._index.search(query_vector, effective_k)

            result_ids = []
            result_scores = []

            for i in range(len(indices[0])):
                idx = indices[0][i]
                if idx < 0 or idx >= len(self._chunk_ids):
                    continue
                chunk_id = self._chunk_ids[idx]
                if chunk_id in self._deleted_mask:
                    continue
                result_ids.append(chunk_id)
                result_scores.append(float(scores[0][i]))
                if len(result_ids) >= top_k:
                    break

            return result_ids, result_scores

    def cleanup_deleted(self):
        with self._lock:
            if not self._deleted_mask:
                return

            valid_indices = []
            valid_chunk_ids = []

            for i, cid in enumerate(self._chunk_ids):
                if cid not in self._deleted_mask:
                    valid_indices.append(i)
                    valid_chunk_ids.append(cid)

            if not valid_indices:
                self._index = self._create_flat_index()
                self._chunk_ids = []
                self._deleted_mask = set()
                self._use_ivf = False
                return

            if self._index.ntotal > 0:
                xb = faiss.rev_swig_ptr(self._index.get_xb(), self._index.ntotal * self.dimension)
                xb = np.array(xb).reshape(self._index.ntotal, self.dimension).astype(np.float32)
                valid_vectors = xb[valid_indices]

                self._index = self._create_flat_index()
                self._index.add(valid_vectors)
                self._use_ivf = False

            self._chunk_ids = valid_chunk_ids
            self._deleted_mask = set()

    def delete(self):
        with self._lock:
            if os.path.exists(self._index_path):
                try:
                    os.remove(self._index_path)
                except Exception:
                    pass
            if os.path.exists(self._meta_path):
                try:
                    os.remove(self._meta_path)
                except Exception:
                    pass
            self._index = None
            self._chunk_ids = []
            self._deleted_mask = set()


_index_cache: Dict[str, VectorIndex] = {}
_index_cache_lock = threading.RLock()


def get_vector_index(knowledge_base_id: str, dimension: int = 384) -> VectorIndex:
    with _index_cache_lock:
        if knowledge_base_id not in _index_cache:
            idx = VectorIndex(knowledge_base_id, dimension)
            idx.load()
            _index_cache[knowledge_base_id] = idx
        return _index_cache[knowledge_base_id]


def remove_vector_index(knowledge_base_id: str):
    with _index_cache_lock:
        if knowledge_base_id in _index_cache:
            _index_cache[knowledge_base_id].delete()
            del _index_cache[knowledge_base_id]
        else:
            tmp = VectorIndex(knowledge_base_id, 384)
            tmp.delete()
