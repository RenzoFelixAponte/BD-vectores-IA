"""Codebook (vocabulario de visual/acoustic words) via K-Means, a mano.

Agrupa TODOS los descriptores locales de la coleccion en k centroides. Cada
centroide es una 'palabra' (visual word / acoustic word). Cuantizar = asignar un
descriptor a su centroide mas cercano.

K-Means escrito a mano (init k-means++ + asignacion + actualizacion + convergencia),
sin librerias de clustering. numpy se usa solo para las operaciones vectoriales.
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np


class Vocabulary:
    def __init__(self, k: int = 256, max_iter: int = 50, tol: float = 1e-4, seed: int = 42):
        """k = numero de palabras del codebook (impacta precision vs costo/dimension)."""
        self.k = k
        self.max_iter = max_iter
        self.tol = tol
        self.seed = seed
        self.centroids: np.ndarray | None = None  # (k, dim) tras fit()

    # ------------------------------------------------------------------
    # Entrenamiento
    # ------------------------------------------------------------------
    def fit(self, descriptors) -> "Vocabulary":
        """Entrena los k centroides con K-Means (Lloyd) e init k-means++.

        Entrada: descriptors  matriz (n, dim) con todos los descriptores locales.
        """
        data = np.asarray(descriptors, dtype=np.float64)
        if data.ndim != 2:
            raise ValueError("descriptors debe ser una matriz (n, dim)")
        n = data.shape[0]
        if n < self.k:
            raise ValueError(f"se necesitan al menos k={self.k} descriptores, hay {n}")

        rng = np.random.default_rng(self.seed)
        centroids = self._kmeanspp_init(data, rng)

        for _ in range(self.max_iter):
            labels = self._assign(data, centroids)
            new_centroids = self._update(data, labels, centroids, rng)
            shift = float(np.sqrt(((new_centroids - centroids) ** 2).sum(axis=1)).max())
            centroids = new_centroids
            if shift <= self.tol:
                break

        self.centroids = centroids.astype(np.float32)
        return self

    def _kmeanspp_init(self, data: np.ndarray, rng) -> np.ndarray:
        """Inicializacion k-means++ (a mano): centroides bien separados."""
        n = data.shape[0]
        centroids = [data[rng.integers(n)]]
        # Distancia minima al centroide ya elegido mas cercano.
        closest_sq = ((data - centroids[0]) ** 2).sum(axis=1)
        for _ in range(1, self.k):
            probs = closest_sq / closest_sq.sum() if closest_sq.sum() > 0 else None
            idx = rng.choice(n, p=probs) if probs is not None else rng.integers(n)
            centroids.append(data[idx])
            dist_sq = ((data - data[idx]) ** 2).sum(axis=1)
            closest_sq = np.minimum(closest_sq, dist_sq)
        return np.asarray(centroids, dtype=np.float64)

    def _assign(self, data: np.ndarray, centroids: np.ndarray) -> np.ndarray:
        """Asigna cada punto a su centroide mas cercano (argmin de distancia)."""
        # ||x - c||^2 = ||x||^2 - 2 x.c + ||c||^2  -> solo importa -2 x.c + ||c||^2
        c_sq = (centroids ** 2).sum(axis=1)
        # producto (n, k); por bloques para no explotar memoria en colecciones grandes
        labels = np.empty(data.shape[0], dtype=np.int32)
        block = 4096
        for start in range(0, data.shape[0], block):
            chunk = data[start:start + block]
            dist = c_sq[None, :] - 2.0 * (chunk @ centroids.T)
            labels[start:start + block] = np.argmin(dist, axis=1)
        return labels

    def _update(self, data: np.ndarray, labels: np.ndarray, centroids: np.ndarray, rng) -> np.ndarray:
        """Recalcula cada centroide como la media de sus puntos asignados."""
        new_centroids = centroids.copy()
        for j in range(self.k):
            members = data[labels == j]
            if len(members) > 0:
                new_centroids[j] = members.mean(axis=0)
            else:
                # Centroide vacio: re-sembrar con un punto aleatorio (evita clusters muertos).
                new_centroids[j] = data[rng.integers(data.shape[0])]
        return new_centroids

    # ------------------------------------------------------------------
    # Cuantizacion
    # ------------------------------------------------------------------
    def quantize(self, descriptors) -> list[int]:
        """Asigna cada descriptor a su palabra mas cercana. Salida: lista de word_id."""
        if self.centroids is None:
            raise RuntimeError("el codebook no esta entrenado/cargado")
        data = np.asarray(descriptors, dtype=np.float64)
        if data.size == 0:
            return []
        if data.ndim == 1:
            data = data[None, :]
        return self._assign(data, self.centroids.astype(np.float64)).tolist()

    # ------------------------------------------------------------------
    # Persistencia binaria propia (header k,dim + centroides float32)
    # ------------------------------------------------------------------
    def save(self, path: str | Path) -> None:
        if self.centroids is None:
            raise RuntimeError("no hay codebook entrenado que guardar")
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        k, dim = self.centroids.shape
        with out.open("wb") as f:
            f.write(struct.pack("<ii", k, dim))
            f.write(self.centroids.astype(np.float32).tobytes())

    @classmethod
    def load(cls, path: str | Path) -> "Vocabulary":
        with Path(path).open("rb") as f:
            k, dim = struct.unpack("<ii", f.read(8))
            centroids = np.frombuffer(f.read(k * dim * 4), dtype=np.float32).reshape(k, dim)
        vocab = cls(k=k)
        vocab.centroids = centroids.copy()
        return vocab
