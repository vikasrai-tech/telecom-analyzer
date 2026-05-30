"""
RAG Retriever — singleton interface over SpecEmbedder.
Call retrieve() anywhere; index is built lazily on first call.
"""

import logging
from typing import List, Dict, Any

from .embedder import SpecEmbedder

logger = logging.getLogger(__name__)

_embedder: SpecEmbedder = None


def _get_embedder() -> SpecEmbedder:
    global _embedder
    if _embedder is None:
        _embedder = SpecEmbedder()
        _embedder.build_index()
    return _embedder


def retrieve(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """
    Retrieve top-k most relevant 3GPP spec chunks for the given query.

    Returns list of chunk dicts with fields:
      spec, section, topic, keywords, text, relevance_score
    """
    try:
        return _get_embedder().search(query, top_k=top_k)
    except Exception as e:
        logger.error(f"Retrieval failed: {e}")
        return []


def reset():
    """Force index rebuild (e.g., after knowledge base update)."""
    global _embedder
    _embedder = None
