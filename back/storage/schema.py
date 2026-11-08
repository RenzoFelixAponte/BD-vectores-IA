import struct
from enum import Enum


class FieldType(Enum):
    INT = "INT"
    FLOAT = "FLOAT"
    VARCHAR = "VARCHAR"
    BOOL = "BOOL"


# Bytes fijos por tipo (VARCHAR usa el tamaño declarado por el usuario)
_TYPE_SIZES = {
    FieldType.INT: 4,
    FieldType.FLOAT: 8,
    FieldType.BOOL: 1,
}

# Formato struct por tipo (big-endian para portabilidad)
_TYPE_FORMATS = {
    FieldType.INT: ">i",
    FieldType.FLOAT: ">d",
    FieldType.BOOL: ">?",
}


class Field:
    """Un campo del schema: nombre, tipo y tamaño en bytes."""

    def __init__(self, name: str, field_type: FieldType, max_length: int = None):
        self.name = name
        self.field_type = field_type

        if field_type == FieldType.VARCHAR:
            if max_length is None:
                raise ValueError(f"VARCHAR '{name}' requiere max_length")
            self.size = max_length
        else:
            self.size = _TYPE_SIZES[field_type]

    def __repr__(self):
        return f"Field({self.name}, {self.field_type.value}, {self.size}B)"


class Schema:
    """
    Define la estructura de una tabla.

    Ejemplo:
        Schema([
            Field("id",     FieldType.INT),
            Field("nombre", FieldType.VARCHAR, max_length=50),
            Field("saldo",  FieldType.FLOAT),
            Field("activo", FieldType.BOOL),
        ], primary_key="id")

    record_size es fijo: cada registro ocupa exactamente esos bytes en disco.
    """

    def __init__(self, fields: list[Field], primary_key: str):
        self.fields = fields
        self.primary_key = primary_key
        self._field_map: dict[str, Field] = {f.name: f for f in fields}

        if primary_key not in self._field_map:
            raise ValueError(f"primary_key '{primary_key}' no existe en los campos")

        self.record_size: int = sum(f.size for f in fields)

    # ------------------------------------------------------------------
    # Serialización: dict → bytes (tamaño fijo = record_size)
    # ------------------------------------------------------------------
    def serialize(self, record: dict) -> bytes:
        """Convierte un registro Python en bytes de tamaño fijo."""
        parts: list[bytes] = []
        for field in self.fields:
            value = record.get(field.name)
            if value is None:
                # campo ausente → relleno de ceros
                parts.append(b"\x00" * field.size)
                continue

            if field.field_type == FieldType.VARCHAR:
                encoded = str(value).encode("utf-8")[: field.size]
                parts.append(encoded.ljust(field.size, b"\x00"))
            else:
                parts.append(struct.pack(_TYPE_FORMATS[field.field_type], value))

        raw = b"".join(parts)
        assert len(raw) == self.record_size, (
            f"Error interno: serializado {len(raw)}B, esperado {self.record_size}B"
        )
        return raw

    # ------------------------------------------------------------------
    # Deserialización: bytes → dict
    # ------------------------------------------------------------------
    def deserialize(self, data: bytes) -> dict:
        """Convierte bytes leídos de disco en un registro Python."""
        if len(data) < self.record_size:
            raise ValueError(
                f"Datos insuficientes: {len(data)}B, esperado {self.record_size}B"
            )
        record: dict = {}
        offset = 0
        for field in self.fields:
            chunk = data[offset : offset + field.size]
            if field.field_type == FieldType.VARCHAR:
                record[field.name] = chunk.rstrip(b"\x00").decode("utf-8")
            else:
                record[field.name] = struct.unpack(_TYPE_FORMATS[field.field_type], chunk)[0]
            offset += field.size
        return record

    def get_field(self, name: str) -> Field:
        if name not in self._field_map:
            raise KeyError(f"Campo '{name}' no existe en el schema")
        return self._field_map[name]

    def __repr__(self):
        cols = ", ".join(f.name for f in self.fields)
        return f"Schema([{cols}], pk={self.primary_key}, {self.record_size}B/registro)"
