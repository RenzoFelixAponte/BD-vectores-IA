"""Preparacion de colecciones de prueba para la experimentacion.

Genera subconjuntos reproducibles a distintas escalas (p. ej. 1k / 10k / N) para
medir escalabilidad, tanto de texto como de multimedia.
"""

from __future__ import annotations


def prepare_text_collection(source: str, scale: int, seed: int = 42):
    """Devuelve una coleccion de documentos (doc_id, texto) de tamano 'scale'."""
    raise NotImplementedError


def prepare_media_collection(source_dir: str, scale: int, seed: int = 42):
    """Devuelve una coleccion de items (doc_id, ruta_archivo) de tamano 'scale'."""
    raise NotImplementedError


def load_query_set(path: str):
    """Carga el conjunto fijo de consultas (texto o rutas) + relevancia conocida."""
    raise NotImplementedError
