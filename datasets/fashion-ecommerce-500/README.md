# Fashion E-commerce Sample 500

Subconjunto pequeno del dataset Fashion Product Images para probar la busqueda visual e-commerce sin subir el dataset completo.

## Contenido

- `products.csv`: 500 productos con metadatos y ruta local de imagen.
- `images/`: imagenes `.jpg` referenciadas por `products.csv`.

## Columnas

- `id`: identificador del producto.
- `name`: nombre visible del producto.
- `gender`: segmento.
- `category`: categoria principal.
- `subcategory`: subcategoria.
- `article_type`: tipo de articulo.
- `color`: color base.
- `season`: temporada.
- `usage`: uso.
- `image_path`: ruta relativa de la imagen, lista para cargar como columna `IMAGE`.

## Uso esperado

Crear una tabla con `image_path IMAGE`, importar `products.csv` y construir un indice:

```sql
CREATE INDEX idx_products_image ON products (image_path) USING MULTIMEDIA;
```
