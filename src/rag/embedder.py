"""
RAG Embedder — builds and queries a FAISS index over 3GPP spec chunks.
Uses sentence-transformers for embeddings (all-MiniLM-L6-v2, 80 MB).
"""

import logging
from typing import List, Dict, Any

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

from .knowledge_base import SPEC_CHUNKS

logger = logging.getLogger(__name__)

MODEL_NAME = "all-MiniLM-L6-v2"   # fast 80 MB model — downloads once


class SpecEmbedder:
    """
    Singleton embedding engine.
    Call build_index() once at startup, then search() freely.
    """

    def __init__(self, model_name: str = MODEL_NAME):
        logger.info(f"Loading embedding model: {model_name}")
        self.model  = SentenceTransformer(model_name)
        self.index  = None
        self.chunks: List[Dict[str, Any]] = []

    def build_index(self, chunks: List[Dict[str, Any]] = None) -> None:
        if chunks is None:
            chunks = SPEC_CHUNKS
        self.chunks = chunks

        texts = [c["text"] for c in chunks]
        logger.info(f"Embedding {len(texts)} spec chunks...")
        embeddings = self.model.encode(
            texts,
            normalize_embeddings=True,   # cosine via inner product
            show_progress_bar=False,
            batch_size=32,
        )
        embeddings = embeddings.astype(np.float32)

        dim = embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dim)   # inner product = cosine similarity
        self.index.add(embeddings)
        logger.info(f"FAISS index built: {self.index.ntotal} vectors, dim={dim}")

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        if self.index is None:
            logger.warning("Index not built — call build_index() first")
            return []

        q_emb = self.model.encode(
            [query], normalize_embeddings=True, show_progress_bar=False
        ).astype(np.float32)

        scores, indices = self.index.search(q_emb, top_k)

        results = []
        for idx, score in zip(indices[0], scores[0]):
            if idx < 0 or idx >= len(self.chunks):
                continue
            chunk = dict(self.chunks[idx])
            chunk["relevance_score"] = round(float(score), 4)
            results.append(chunk)

        return results
