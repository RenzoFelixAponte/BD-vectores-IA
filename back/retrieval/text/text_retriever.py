"""Orquestador de la recuperacion textual (punto de entrada del operador @@).

Lo invoca executor._exec_text_search. Une tokenizer + inverted_index + cosine_ranker
y devuelve los (doc_id, score) top-k para que el executor resuelva las filas.
"""

from __future__ import annotations

from pathlib import Path

from .chunker import Chunker
from .cosine_ranker import CosineRanker
from .inverted_index import InvertedIndex
from .spimi import SpimiBuilder
from .tokenizer import Tokenizer


class TextRetriever:
    def __init__(self, index: InvertedIndex, tokenizer: Tokenizer, chunker: Chunker | None = None):
        self.index = index
        self.tokenizer = tokenizer
        self.chunker = chunker
        self.ranker = CosineRanker(index, chunker=chunker)

    def search(self, query_text: str, k: int, method: str | None = None, documents=None) -> list[tuple[int, float]]:
        """Top-k (doc_id, score) por coseno.

        method:
            None | 'inverted'  -> ranking con el indice invertido (rapido)
            'sequential'       -> ranking por scan completo (requiere `documents`)
        """
        terms = self.tokenizer.process(query_text)
        if method == "sequential":
            if documents is None:
                raise ValueError("el modo secuencial requiere la coleccion `documents`")
            return self.ranker.rank_sequential(terms, k, documents)
        return self.ranker.rank(terms, k)

    @classmethod
    def build(cls, documents, index_dir: str, tokenizer: Tokenizer,
              block_size_postings: int = 100_000,
              chunker: Chunker | None = None) -> "TextRetriever":
        """Construye el indice (via SpimiBuilder) y retorna un retriever listo.

        documents: iterable de (doc_id:int, raw_text:str). Se tokeniza cada uno con
        el mismo tokenizer antes de indexar. Lo usa CREATE INDEX ... USING INVERTED.

        chunker: si se pasa, cada documento se parte en fragmentos y CADA fragmento
        se indexa como un documento propio (chunk_id). Se persiste un chunk_map que
        permite re-agregar los resultados a su documento padre en la consulta.
        """
        builder = SpimiBuilder(index_dir, block_size_postings=block_size_postings)

        if chunker is None:
            tokenized = ((doc_id, tokenizer.process(text)) for doc_id, text in documents)
            index = builder.build(tokenized)
            return cls(index, tokenizer)

        # --- Construccion fragmentada ---
        chunk_map: dict[int, int] = {}

        def chunk_docs():
            next_chunk_id = 0
            for doc_id, text in documents:
                terms = tokenizer.process(text)
                for chunk_terms in chunker.chunk_terms(terms):
                    chunk_map[next_chunk_id] = doc_id
                    yield next_chunk_id, chunk_terms
                    next_chunk_id += 1

        chunk_meta = {"chunked": True, "chunk_size": chunker.chunk_size, "overlap": chunker.overlap}
        index = builder.build(chunk_docs(), chunk_map=chunk_map, chunk_meta=chunk_meta)
        return cls(index, tokenizer, chunker=chunker)

    @classmethod
    def open(cls, index_dir: str, tokenizer: Tokenizer) -> "TextRetriever":
        """Abre un indice ya construido en disco (detecta chunking desde meta.json)."""
        index = InvertedIndex(str(Path(index_dir)))
        index.load()
        chunker = None
        if index.meta.get("chunked"):
            chunker = Chunker(
                chunk_size=index.meta.get("chunk_size", 200),
                overlap=index.meta.get("overlap", 40),
            )
        return cls(index, tokenizer, chunker=chunker)
