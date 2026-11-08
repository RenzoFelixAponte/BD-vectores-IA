"""Preprocesamiento de audio: eliminación de silencio, normalización, etc.

Operaciones opcionales antes de la extracción de MFCC para mejorar la calidad
de los descriptores.
"""
from __future__ import annotations

import numpy as np

class AudioPreprocessor:
    """Preprocesador de audio con operaciones básicas"""
    
    @staticmethod
    def normalize(signal: np.ndarray) -> np.ndarray:
        """Normaliza la amplitud del audio al rango [-1, 1]"""
        if signal.size == 0:
            return 
        max_val = np.max(np.abs(signal))
        if max_val > 1e-10:
            return signal / max_val
        return signal
    
    @staticmethod
    def trim_to_duration(signal: np.ndarray, sr: int, max_duration: float = 30.0) -> np.ndarray:
        """Recorta el audio a una duración máxima."""
        max_samples = int(sr * max_duration)
        if len(signal) > max_samples:
            return signal[:max_samples]
        return signal
    
    @staticmethod
    def remove_silence(signal: np.ndarray, sr: int, 
                       threshold_db: float = -40, 
                       hop_length: int = 512) -> np.ndarray:
        """Elimina segmentos de silencio del audio"""
        if signal.size == 0:
            return signal

        # Calcular energía en ventanas
        window_size = hop_length * 2
        energy = np.array([
            np.sum(signal[i:i + window_size] ** 2)
            for i in range(0, max(1, len(signal) - window_size), hop_length)
        ])
        
        # Si no hay energía, retornar señal original
        if energy.size == 0 or np.max(energy) < 1e-10:
            return signal

        # Normalizar energía a dB
        energy_db = 10 * np.log10(energy / np.max(energy) + 1e-10)

        # Encontrar índices donde la energía supera el umbral
        threshold_linear = 10 ** (threshold_db / 10)
        mask = energy > threshold_linear * np.max(energy)

        if not np.any(mask):
            return signal

        # Encontrar el primer y último segmento no silencioso
        start_idx = np.argmax(mask) * hop_length
        end_idx = (len(mask) - np.argmax(mask[::-1])) * hop_length
        end_idx = min(end_idx, len(signal))
        
        return signal[start_idx:end_idx]
    
    @staticmethod
    def trim_silence(signal: np.ndarray, sr: int, 
                     top_db: float = 20, 
                     hop_length: int = 512) -> np.ndarray:
        """Recorta el silencio al inicio y final del audio"""
        if signal.size == 0:
            return signal

        # Calcular energía en ventanas
        window_size = hop_length * 2
        energy = np.array([
            np.sum(signal[i:i + window_size] ** 2)
            for i in range(0, max(1, len(signal) - window_size), hop_length)
        ])

        if energy.size == 0 or np.max(energy) < 1e-10:
            return signal

        # Encontrar pico máximo
        peak = np.max(energy)
        threshold = peak * (10 ** (-top_db / 10))

        # Encontrar primer y último índice con energía > umbral
        non_silent = np.where(energy > threshold)[0]
        if non_silent.size == 0:
            return signal

        start_frame = non_silent[0]
        end_frame = non_silent[-1] + 1

        start_sample = max(0, start_frame * hop_length - hop_length // 2)
        end_sample = min(len(signal), end_frame * hop_length + hop_length // 2)

        return signal[start_sample:end_sample]
    
    @staticmethod
    def resample_if_needed(signal: np.ndarray, original_sr: int, 
                           target_sr: int = 22050) -> tuple[np.ndarray, int]:
        """Re-muestrea el audio si es necesario"""
        if original_sr == target_sr or signal.size == 0:
            return signal, original_sr

        # Interpolación lineal simple (para casos donde no se puede usar librosa)
        from scipy import signal as scipy_signal
        # Usar scipy.signal.resample si está disponible, de lo contrario usar interpolación simple
        try:
            new_length = int(len(signal) * target_sr / original_sr)
            resampled = scipy_signal.resample(signal, new_length)
            return resampled.astype(np.float32), target_sr
        except (ImportError, Exception):
            # Fallback: interpolación lineal simple
            old_indices = np.arange(len(signal))
            new_indices = np.linspace(0, len(signal) - 1, int(len(signal) * target_sr / original_sr))
            resampled = np.interp(new_indices, old_indices, signal)
            return resampled.astype(np.float32), target_sr
        
    def process(self, signal: np.ndarray, sr: int,
                normalize: bool = True,
                trim_silence: bool = True,
                remove_internal_silence: bool = False,
                max_duration: float | None = 30.0,
                silence_threshold_db: float = -40) -> np.ndarray:
        """Pipeline completo de preprocesamiento"""
        if signal.size == 0:
            return signal

        # Recortar duración
        if max_duration is not None:
            signal = self.trim_to_duration(signal, sr, max_duration)

        # Recortar silencio
        if remove_internal_silence:
            signal = self.remove_silence(signal, sr, threshold_db=silence_threshold_db)

        # Recortar silencio inicial y final
        if trim_silence:
            signal = self.trim_silence(signal, sr, top_db=abs(silence_threshold_db))

        # Normalizar
        if normalize:
            signal = self.normalize(signal)

        return signal
