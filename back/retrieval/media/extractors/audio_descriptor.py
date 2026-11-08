"""Descriptores locales de AUDIO (MFCC con ventana deslizante).

Cada audio produce una secuencia de vectores MFCC (uno por ventana de ~100-200 ms),
analogos a los keypoints SIFT: son las 'palabras' antes de cuantizar contra el
codebook acustico. librosa se usa SOLO para extraer la senal cruda; el resto (codebook,
histograma, KNN) se hace a mano.
"""

from __future__ import annotations

import numpy as np


class AudioDescriptorExtractor:
    def __init__(self, sample_rate: int = 22050, n_mfcc: int = 20,
                 window_ms: int = 100, hop_ms: int = 50, max_duration: float | None = 30.0):
        """Ventana deslizante de ~100-200 ms; cada ventana -> un vector MFCC."""
        self.sample_rate = sample_rate
        self.n_mfcc = n_mfcc
        self.window_ms = window_ms
        self.hop_ms = hop_ms
        self.max_duration = max_duration

    def extract(self, audio_path: str) -> np.ndarray:
        """Extrae descriptores MFCC.

        Salida: matriz (n_frames, n_mfcc) float32. Vacia si el audio no se puede leer.
        """
        import librosa  # import diferido

        try:
            signal, sr = librosa.load(str(audio_path), sr=self.sample_rate,
                                      mono=True, duration=self.max_duration)
        except (ImportError, ModuleNotFoundError):
            # Problema de entorno (dependencia faltante): NO lo silenciamos,
            # así el error es visible en vez de "no se extrajeron descriptores".
            raise
        except Exception:
            # Archivo corrupto/ilegible puntual: se omite ese item.
            return np.empty((0, self.n_mfcc), dtype=np.float32)
        if signal.size == 0:
            return np.empty((0, self.n_mfcc), dtype=np.float32)

        n_fft = max(256, int(sr * self.window_ms / 1000))
        hop_length = max(128, int(sr * self.hop_ms / 1000))
        mfcc = librosa.feature.mfcc(
            y=signal, sr=sr, n_mfcc=self.n_mfcc,
            n_fft=min(n_fft, len(signal)), hop_length=hop_length,
        )
        descriptors = mfcc.T  # (n_frames, n_mfcc)
        if descriptors.size == 0:
            return np.empty((0, self.n_mfcc), dtype=np.float32)
        return np.nan_to_num(descriptors).astype(np.float32)
