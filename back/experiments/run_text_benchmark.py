"""Benchmark de recuperacion de texto.

Compara, a varias escalas y con el mismo conjunto de consultas:
  - indice invertido propio (coseno)        [USING INVERTED]
  - scan secuencial + coseno (baseline)      [USING SEQUENTIAL]
  - PostgreSQL full-text (GIN)               [referencia externa]

Mide: latencia (media/mediana/p95), throughput, precision@k / recall@k,
tamano de indice y tiempo de construccion. Escribe resultados a results/.
"""

from __future__ import annotations


def run(scales: list[int], k: int, queries, repeats: int = 3) -> dict:
    """Ejecuta el benchmark completo y devuelve un dict de metricas por motor/escala."""
    raise NotImplementedError


def main() -> None:
    raise NotImplementedError


if __name__ == "__main__":
    main()
