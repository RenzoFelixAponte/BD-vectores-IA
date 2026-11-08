"""Benchmark de recuperacion multimedia (imagen / audio).

Compara, a varias escalas y con el mismo conjunto de consultas:
  - KNN indexado (Bag of Words + indice invertido de codewords)  [USING MULTIMEDIA]
  - KNN secuencial (fuerza bruta)                                 [USING SEQUENTIAL]

Mide: latencia, throughput, precision@k, tamano de indice, y el efecto del tamano
del codebook k (maldicion de la dimensionalidad). Escribe resultados a results/.
"""

from __future__ import annotations


def run(scales: list[int], k: int, codebook_sizes: list[int], queries, repeats: int = 3) -> dict:
    """Ejecuta el benchmark y devuelve metricas por motor / escala / tamano de codebook."""
    raise NotImplementedError


def main() -> None:
    raise NotImplementedError


if __name__ == "__main__":
    main()
