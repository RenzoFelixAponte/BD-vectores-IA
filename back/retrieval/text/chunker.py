"""Fragmentacion (chunking) de documentos de texto para el indice invertido.

Motivacion: un documento largo (p. ej. la letra completa de una cancion o un PDF)
diluye la senal TF-IDF: un termino relevante que aparece en un parrafo pesa poco
respecto al total del documento. Al partir el texto en fragmentos (chunks) mas
cortos y tratar CADA chunk como un "documento" del indice, el ranking premia la
coincidencia local. Luego se re-agrega al documento padre tomando su MEJOR chunk.

Se trabaja sobre la lista de terminos YA tokenizada (post-normalizacion/stopwords),
no sobre el texto crudo, para que las fronteras de los chunks sean IDENTICAS tanto
al construir el indice como al escanear en modo secuencial (mismo tokenizer -> mismos
tokens -> mismos cortes). El tamano se mide en tokens.
"""

from __future__ import annotations


class Chunker:
    def __init__(self, chunk_size: int = 200, overlap: int = 40):
        """chunk_size: tokens por fragmento. overlap: tokens compartidos entre
        fragmentos consecutivos (ventana deslizante) para no cortar contexto en la
        frontera. Debe cumplirse 0 <= overlap < chunk_size.
        """
        if chunk_size <= 0:
            raise ValueError("chunk_size debe ser positivo")
        if not (0 <= overlap < chunk_size):
            raise ValueError("overlap debe cumplir 0 <= overlap < chunk_size")
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_terms(self, terms: list[str]) -> list[list[str]]:
        """Parte una lista de terminos en fragmentos solapados.

        - Lista vacia -> [] (el documento no aporta postings, igual que antes).
        - Si cabe en un solo fragmento -> [terms] (sin costo extra).
        """
        if not terms:
            return []
        if len(terms) <= self.chunk_size:
            return [terms]
        step = self.chunk_size - self.overlap
        chunks: list[list[str]] = []
        for start in range(0, len(terms), step):
            chunks.append(terms[start:start + self.chunk_size])
            if start + self.chunk_size >= len(terms):
                break
        return chunks
