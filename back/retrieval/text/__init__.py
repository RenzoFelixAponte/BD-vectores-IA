"""Indice invertido para TEXTO: SPIMI en memoria secundaria + ranking por coseno.

Flujo de construccion (offline):
    tokenizer  -> spimi (bloques en disco + merge) -> inverted_index (postings en disco)

Flujo de consulta (online, operador @@):
    text_retriever -> tokenizer(consulta) -> inverted_index(postings) -> cosine_ranker(top-k)
"""

from .tokenizer import Tokenizer
from .chunker import Chunker
from .spimi import SpimiBuilder
from .inverted_index import InvertedIndex
from .cosine_ranker import CosineRanker
from .text_retriever import TextRetriever

__all__ = ["Tokenizer", "Chunker", "SpimiBuilder", "InvertedIndex", "CosineRanker", "TextRetriever"]
