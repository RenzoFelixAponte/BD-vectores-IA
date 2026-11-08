"""SPIMI: Single-Pass In-Memory Indexing (construccion en memoria secundaria).

Metodo optimizado para construir el indice invertido cuando la coleccion NO entra
en RAM. Implementado a mano (solo stdlib):

  1. Recorrer los documentos UNA vez acumulando postings en RAM hasta llenar un
     bloque (limite de postings).
  2. Al llenarse, ordenar por termino y volcar el bloque a disco (JSONL ordenado).
  3. Repetir -> varios bloques ordenados en disco.
  4. Merge multi-via (k-way) de los bloques en un unico postings.jsonl final,
     combinando las listas del mismo termino. Se registran offsets (diccionario),
     df/idf y las normas TF-IDF de cada documento.

El merge usa un heap sobre los primeros terminos de cada bloque: nunca carga todos
los postings en memoria a la vez.
"""

from __future__ import annotations

import heapq
import json
import math
from collections import defaultdict
from pathlib import Path

from .inverted_index import InvertedIndex


class SpimiBuilder:
    def __init__(self, output_dir: str, block_size_postings: int = 100_000):
        self.output_dir = Path(output_dir)
        self.blocks_dir = self.output_dir / "blocks"
        self.block_size_postings = block_size_postings

    def build(self, documents, chunk_map: dict[int, int] | None = None,
              chunk_meta: dict | None = None) -> InvertedIndex:
        """Construye el indice invertido completo.

        Entrada: documents iterable de (doc_id:int, terms:list[str]).
                 Cuando hay chunking, doc_id es el chunk_id y `chunk_map` mapea cada
                 chunk_id a la clave primaria del documento padre.
        Salida:  InvertedIndex apuntando al indice final en disco.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.blocks_dir.mkdir(parents=True, exist_ok=True)
        for old in self.blocks_dir.glob("block-*.jsonl"):
            old.unlink()

        # ---- Fase 1: acumular y volcar bloques ----
        block: dict[str, list[list[int]]] = defaultdict(list)  # term -> [[doc_id, tf], ...]
        postings_in_block = 0
        block_paths: list[Path] = []
        num_docs = 0

        for doc_id, terms in documents:
            num_docs += 1
            tf: dict[str, int] = defaultdict(int)
            for t in terms:
                tf[t] += 1
            for term, freq in tf.items():
                block[term].append([doc_id, freq])
                postings_in_block += 1
            if postings_in_block >= self.block_size_postings:
                block_paths.append(self._flush_block(block, len(block_paths)))
                block = defaultdict(list)
                postings_in_block = 0

        if block:
            block_paths.append(self._flush_block(block, len(block_paths)))

        # ---- Fase 2: merge k-way + diccionario + idf ----
        postings_path = self.output_dir / "postings.jsonl"
        dictionary = self._merge_blocks(block_paths, postings_path, num_docs)

        # ---- Fase 3: normas TF-IDF por documento (segunda pasada) ----
        norms = self._compute_document_norms(postings_path, dictionary)

        (self.output_dir / "dictionary.json").write_text(
            json.dumps(dictionary), encoding="utf-8"
        )
        (self.output_dir / "norms.json").write_text(
            json.dumps({str(d): n for d, n in norms.items()}), encoding="utf-8"
        )
        meta = {"num_docs": num_docs}
        if chunk_meta:
            meta.update(chunk_meta)
        (self.output_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

        chunk_map_path = self.output_dir / "chunk_map.json"
        if chunk_map is not None:
            chunk_map_path.write_text(
                json.dumps({str(cid): pk for cid, pk in chunk_map.items()}), encoding="utf-8"
            )
        elif chunk_map_path.is_file():
            # Reconstruccion sin chunking sobre una carpeta previa fragmentada: limpiar.
            chunk_map_path.unlink()

        index = InvertedIndex(str(self.output_dir))
        index.load()
        return index

    def _flush_block(self, block: dict[str, list[list[int]]], block_number: int) -> Path:
        """Ordena por termino y vuelca un bloque parcial a disco. Devuelve su ruta."""
        path = self.blocks_dir / f"block-{block_number:05d}.jsonl"
        with path.open("w", encoding="utf-8", newline="\n") as f:
            for term in sorted(block):
                f.write(json.dumps({"t": term, "p": block[term]}) + "\n")
        return path

    @staticmethod
    def _iter_block(stream):
        for line in stream:
            payload = json.loads(line)
            yield payload["t"], payload["p"]

    def _merge_blocks(self, block_paths: list[Path], output_path: Path, num_docs: int) -> dict:
        """Merge k-way de bloques ordenados -> postings.jsonl final + diccionario.

        Devuelve dictionary: term -> {df, idf, offset} (offset en bytes del archivo).
        """
        streams = [p.open("r", encoding="utf-8") for p in block_paths]
        iterators = [self._iter_block(s) for s in streams]
        heap: list[tuple[str, int, list]] = []
        dictionary: dict[str, dict] = {}

        try:
            for i, it in enumerate(iterators):
                try:
                    term, postings = next(it)
                    heapq.heappush(heap, (term, i, postings))
                except StopIteration:
                    pass

            with output_path.open("w", encoding="utf-8", newline="\n") as out:
                while heap:
                    term, i, postings = heapq.heappop(heap)
                    combined = list(postings)
                    consumed = [i]
                    # Junta todas las apariciones del mismo termino entre bloques.
                    while heap and heap[0][0] == term:
                        _, j, more = heapq.heappop(heap)
                        combined.extend(more)
                        consumed.append(j)
                    combined.sort(key=lambda posting: posting[0])

                    df = len(combined)
                    idf = math.log(num_docs / df) + 1.0 if df > 0 else 0.0
                    offset = out.tell()  # byte offset de esta linea -> permite seek
                    out.write(json.dumps({"t": term, "p": combined}) + "\n")
                    dictionary[term] = {"df": df, "idf": idf, "offset": offset}

                    for j in consumed:
                        try:
                            nt, np_ = next(iterators[j])
                            heapq.heappush(heap, (nt, j, np_))
                        except StopIteration:
                            pass
        finally:
            for s in streams:
                s.close()

        return dictionary

    def _compute_document_norms(self, postings_path: Path, dictionary: dict) -> dict[int, float]:
        """Norma TF-IDF de cada documento: sqrt(sum_t (tfidf_{t,d})^2).

        Segunda pasada leyendo el postings final; peso = (1 + log(tf)) * idf.
        """
        norm_sq: dict[int, float] = defaultdict(float)
        with postings_path.open("r", encoding="utf-8") as f:
            for line in f:
                payload = json.loads(line)
                idf = dictionary[payload["t"]]["idf"]
                for doc_id, tf in payload["p"]:
                    weight = (1.0 + math.log(tf)) * idf
                    norm_sq[doc_id] += weight * weight
        return {doc_id: math.sqrt(v) for doc_id, v in norm_sq.items()}
