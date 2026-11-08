from __future__ import annotations

from pathlib import Path

from back.engine import Database
from back.storage.schema import Field, FieldType, Schema


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "datasets" / "fashion-ecommerce-500" / "products.csv"
TABLE_NAME = "products"
IMAGE_INDEX_NAME = "idx_products_image"


def build_products_table() -> None:
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"No existe el CSV del dataset: {CSV_PATH}")

    db = Database()
    if TABLE_NAME in db.list_tables():
        db.drop_table(TABLE_NAME)
        print(f"Tabla '{TABLE_NAME}' existente eliminada para reconstruir la muestra.")

    schema = Schema(
        [
            Field("id", FieldType.INT),
            Field("name", FieldType.VARCHAR, max_length=160),
            Field("gender", FieldType.VARCHAR, max_length=20),
            Field("category", FieldType.VARCHAR, max_length=40),
            Field("subcategory", FieldType.VARCHAR, max_length=60),
            Field("article_type", FieldType.VARCHAR, max_length=80),
            Field("color", FieldType.VARCHAR, max_length=40),
            Field("season", FieldType.VARCHAR, max_length=20),
            Field("usage", FieldType.VARCHAR, max_length=40),
            Field("image_path", FieldType.VARCHAR, max_length=255),
        ],
        primary_key="id",
    )
    column_definitions = [
        {"name": "id", "type": "INT"},
        {"name": "name", "type": "CHAR", "size": 160},
        {"name": "gender", "type": "CHAR", "size": 20},
        {"name": "category", "type": "CHAR", "size": 40},
        {"name": "subcategory", "type": "CHAR", "size": 60},
        {"name": "article_type", "type": "CHAR", "size": 80},
        {"name": "color", "type": "CHAR", "size": 40},
        {"name": "season", "type": "CHAR", "size": 20},
        {"name": "usage", "type": "CHAR", "size": 40},
        {"name": "image_path", "type": "IMAGE"},
    ]

    table = db.create_table(TABLE_NAME, schema, column_definitions, primary_index_type="bplus")
    rows = db._load_csv(table, str(CSV_PATH))
    print(f"Tabla '{TABLE_NAME}' creada con {rows} productos.")

    summary = db.add_content_index(
        TABLE_NAME,
        IMAGE_INDEX_NAME,
        ["image_path"],
        "multimedia",
        codebook_size=128,
    )
    print(
        f"Indice '{IMAGE_INDEX_NAME}' creado: "
        f"{summary['indexed_items']} imagenes indexadas con k=128."
    )


if __name__ == "__main__":
    build_products_table()
