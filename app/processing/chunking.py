"""Chunking utilities."""

from typing import List


def chunk_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    """Split text into overlapping chunks."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be >= 0 and < chunk_size")

    t = text or ""
    if len(t) <= chunk_size:
        return [t]

    chunks: List[str] = []
    start = 0
    while start < len(t):
        end = min(len(t), start + chunk_size)
        chunks.append(t[start:end])
        if end == len(t):
            break
        start = max(0, end - overlap)
    return chunks


def chunk_if_needed(text: str, max_chars: int, chunk_size: int, overlap: int) -> List[str]:
    """Return [text] if small enough, otherwise overlapping chunks."""
    t = text or ""
    return [t] if len(t) <= max_chars else chunk_text(t, chunk_size, overlap)


def map_reduce_summaries(chunk_summaries: List[str], max_chars: int) -> str:
    """Combine chunk summaries into a reducer input string."""
    combined = "\n\n".join([f"Chunk {i+1}: {s}" for i, s in enumerate(chunk_summaries)])
    return combined if len(combined) <= max_chars else combined[:max_chars]