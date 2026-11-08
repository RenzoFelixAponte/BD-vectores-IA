from __future__ import annotations

from pathlib import Path
import csv
import os
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from back.retrieval.media.extractors.image_descriptor import ImageDescriptorExtractor
from back.retrieval.media.media_retriever import MediaRetriever


DATASET_DIR = Path(os.getenv("FASHION_FULL_DIR", ROOT / "datasets" / "fashion-ecommerce-full"))
STYLES_CSV = Path(os.getenv("FASHION_STYLES_CSV", DATASET_DIR / "styles.csv"))
IMAGES_DIR = Path(os.getenv("FASHION_IMAGES_DIR", DATASET_DIR / "images"))
PRODUCTS_CSV = Path(os.getenv("PRODUCTS_CSV", DATASET_DIR / "products.csv"))
INDEX_DIR = Path(os.getenv("IMAGE_INDEX_PATH", ROOT / "back" / "data" / "products_idx_products_image_full"))

LIMIT = int(os.getenv("LIMIT", "0"))
CODEBOOK_SIZE = int(os.getenv("CODEBOOK_SIZE", "128"))
DESCRIPTOR_SAMPLE = int(os.getenv("DESCRIPTOR_SAMPLE", "200000"))
MAX_KEYPOINTS = int(os.getenv("MAX_KEYPOINTS", "160"))
RESIZE_MAX_SIDE = int(os.getenv("RESIZE_MAX_SIDE", "384"))
SEED = int(os.getenv("SEED", "42"))


def norm(value: str | None) -> str:
    return "" if value is None else str(value).strip()


def build_products_csv() -> list[tuple[int, str]]:
    if not STYLES_CSV.exists():
        raise FileNotFoundError(f"No existe {STYLES_CSV}")
    if not IMAGES_DIR.exists():
        raise FileNotFoundError(f"No existe {IMAGES_DIR}")

    PRODUCTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    items: list[tuple[int, str]] = []
    missing_images = 0

    with STYLES_CSV.open(newline="", encoding="utf-8-sig") as src, PRODUCTS_CSV.open(
        "w", newline="", encoding="utf-8"
    ) as dst:
        reader = csv.DictReader(src)
        fieldnames = [
            "id",
            "name",
            "gender",
            "category",
            "subcategory",
            "article_type",
            "color",
            "season",
            "usage",
            "image_path",
        ]
        writer = csv.DictWriter(dst, fieldnames=fieldnames)
        writer.writeheader()

        for row in reader:
            product_id = int(row["id"])
            image_path = IMAGES_DIR / f"{product_id}.jpg"
            if not image_path.exists():
                missing_images += 1
                continue

            relative_image = image_path.relative_to(ROOT).as_posix()
            writer.writerow({
                "id": product_id,
                "name": norm(row.get("productDisplayName")),
                "gender": norm(row.get("gender")),
                "category": norm(row.get("masterCategory")),
                "subcategory": norm(row.get("subCategory")),
                "article_type": norm(row.get("articleType")),
                "color": norm(row.get("baseColour")),
                "season": norm(row.get("season")),
                "usage": norm(row.get("usage")),
                "image_path": relative_image,
            })
            items.append((product_id, str(ROOT / relative_image)))
            if LIMIT and len(items) >= LIMIT:
                break

    print(
        f"products.csv generado: {PRODUCTS_CSV} | "
        f"items={len(items)} | imagenes_faltantes={missing_images}"
    )
    return items


def main() -> None:
    started = time.perf_counter()
    items = build_products_csv()
    if not items:
        raise RuntimeError("No hay imagenes validas para indexar")

    print(
        "Construyendo indice visual local: "
        f"items={len(items)}, k={CODEBOOK_SIZE}, sample={DESCRIPTOR_SAMPLE}, "
        f"max_keypoints={MAX_KEYPOINTS}, resize={RESIZE_MAX_SIDE}"
    )
    extractor = ImageDescriptorExtractor(
        max_keypoints=MAX_KEYPOINTS,
        resize_max_side=RESIZE_MAX_SIDE,
    )
    MediaRetriever.build(
        items,
        str(INDEX_DIR),
        extractor,
        k=CODEBOOK_SIZE,
        descriptor_sample=DESCRIPTOR_SAMPLE,
        seed=SEED,
    )
    elapsed_min = (time.perf_counter() - started) / 60
    print(f"Indice generado en {INDEX_DIR}")
    print(f"Tiempo total: {elapsed_min:.2f} min")


if __name__ == "__main__":
    main()
