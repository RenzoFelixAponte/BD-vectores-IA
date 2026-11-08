"""Normalizacion linguistica del texto, a mano (solo stdlib `re`, sin NLTK).

Pipeline: minusculas -> quitar acentos/puntuacion -> tokenizar -> quitar stopwords
-> stemming ligero. El MISMO tokenizer se usa al construir el indice y al procesar
la consulta, para que los terminos sean comparables.
"""

from __future__ import annotations

import re

# Conjunto compacto de stopwords ES/EN embebido (se puede ampliar desde archivo).
_STOPWORDS_ES = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "a", "al",
    "y", "o", "u", "e", "que", "en", "con", "por", "para", "se", "su", "sus", "lo",
    "le", "les", "es", "son", "fue", "ser", "como", "mas", "pero", "si", "no", "ya",
    "este", "esta", "estos", "estas", "ese", "esa", "eso", "the", "of", "and",
}
_STOPWORDS_EN = {
    "the", "a", "an", "of", "and", "or", "to", "in", "on", "for", "is", "are", "was",
    "were", "be", "by", "with", "as", "at", "that", "this", "it", "from", "but", "not",
}

# Mapa simple para quitar acentos sin librerias.
_ACCENTS = str.maketrans("áéíóúüñàèìòùâêîôû", "aeiouunaeiouaeiou")

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class Tokenizer:
    def __init__(self, language: str = "spanish", use_stemming: bool = True, min_length: int = 2):
        self.language = language
        self.use_stemming = use_stemming
        self.min_length = min_length
        self.stopwords = set(_STOPWORDS_ES) | set(_STOPWORDS_EN)

    def normalize(self, text: str) -> str:
        """Minusculas + quitar acentos. La puntuacion se descarta al tokenizar."""
        return text.lower().translate(_ACCENTS)

    def tokenize(self, text: str) -> list[str]:
        """Extrae secuencias alfanumericas como tokens (descarta puntuacion)."""
        return _TOKEN_RE.findall(text)

    def remove_stopwords(self, tokens: list[str]) -> list[str]:
        return [t for t in tokens if t not in self.stopwords and len(t) >= self.min_length]

    def stem(self, token: str) -> str:
        """Stemmer ligero a mano: quita plurales y sufijos frecuentes (ES/EN).

        No es Porter completo; es un recortador conservador suficiente para juntar
        variantes morfologicas comunes sin librerias.
        """
        for suffix in ("mente", "ciones", "cion", "es", "s"):
            if len(token) - len(suffix) >= 3 and token.endswith(suffix):
                return token[: -len(suffix)]
        return token

    def process(self, text: str) -> list[str]:
        """Pipeline completo: normalize -> tokenize -> remove_stopwords -> stem.

        Salida: lista final de terminos lista para contar frecuencias (TF).
        """
        tokens = self.remove_stopwords(self.tokenize(self.normalize(text)))
        if self.use_stemming:
            tokens = [self.stem(t) for t in tokens]
        return tokens
