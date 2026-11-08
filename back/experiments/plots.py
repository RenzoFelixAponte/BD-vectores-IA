"""Generacion de graficos comparativos para el informe.

Toma los dicts de metricas de los benchmarks y produce las figuras (latencia,
throughput, precision, escalabilidad, impacto de la dimension). El graficado puede
usar matplotlib: es presentacion, no parte del nucleo algoritmico.
"""

from __future__ import annotations


def plot_latency(results: dict, output_path: str) -> None:
    raise NotImplementedError


def plot_precision(results: dict, output_path: str) -> None:
    raise NotImplementedError


def plot_scalability(results: dict, output_path: str) -> None:
    raise NotImplementedError


def plot_dimensionality(results: dict, output_path: str) -> None:
    """Precision/latencia vs tamano del codebook k (maldicion de la dimensionalidad)."""
    raise NotImplementedError
