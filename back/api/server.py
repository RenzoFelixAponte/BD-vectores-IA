from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from collections import deque
import json as _json
import os
import tempfile
import time
from pathlib import Path as _Path
from uuid import uuid4

from ..engine import Database, Executor
from ..parser import Parser, ParseError
from ..parser.semantic_analyzer import SemanticError
from ..parser.lexical_analyzer import LexError
from ..engine.executor import ExecutionError
from ..indexes import SequentialFile, ExtendibleHashing, BPlusTree, RTree
from ..storage.schema import Field, FieldType, Schema
from ..engine.database import DATA_DIR
from ..parser.ast_nodes import SelectPointRadiusNode, SelectKNNNode
from ..parser.ast_nodes import (
    CreateTableNode, CreateIndexNode, InsertNode, SelectAllNode, SelectEqualNode,
    SelectComparisonNode, SelectRangeNode, SelectPointRadiusNode, SelectKNNNode, DeleteNode,
    DropTableNode, DropIndexNode, ImportFileNode, SelectCountNode,
)

app = FastAPI(title="Mini-SGBD API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

db = Database()
executor = Executor(db)
parser = Parser(db=db)
_metrics_history: deque = deque(maxlen=1000)

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

_NODE_OP = {
    CreateTableNode:       "CREATE TABLE",
    CreateIndexNode:       "CREATE INDEX",
    DropTableNode:         "DROP TABLE",
    DropIndexNode:         "DROP INDEX",
    InsertNode:            "INSERT",
    ImportFileNode:        "IMPORT FILE",
    SelectAllNode:         "SELECT ALL",
    SelectEqualNode:       "SELECT",
    SelectComparisonNode:  "SELECT",
    SelectRangeNode:       "SELECT RANGE",
    SelectPointRadiusNode: "SELECT RADIUS",
    SelectKNNNode:         "SELECT KNN",
    SelectCountNode:       "SELECT COUNT",
    DeleteNode:            "DELETE",
}


def _index_type_name(index) -> str:
    if isinstance(index, SequentialFile):   return "sequential"
    if isinstance(index, ExtendibleHashing): return "hash"
    if isinstance(index, BPlusTree):         return "bplus"
    if isinstance(index, RTree):             return "rtree"
    return "unknown"


def _table_name_from(node) -> str:
    return getattr(node, "table_name", "")


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------

class QueryRequest(BaseModel):
    sql: str


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@app.post("/api/v1/query")
def run_query(req: QueryRequest):
    try:
        node = parser.parse(req.sql)
    except (ParseError, SemanticError, LexError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        result = executor.execute(node)
    except ExecutionError as e:
        raise HTTPException(status_code=422, detail=str(e))

    rows: list[dict] = result["results"]
    stats: dict = result["stats"]
    columns = list(rows[0].keys()) if rows else []

    # Mensaje para operaciones que no retornan filas
    message = None
    node_type = type(node)
    if node_type in (CreateTableNode, CreateIndexNode, DropTableNode, DropIndexNode, InsertNode):
        message = f"{_NODE_OP[node_type]} ejecutado correctamente"
    elif node_type == ImportFileNode:
        imported = rows[0]["imported"] if rows else 0
        message = f"IMPORT FILE: {imported} registros importados"
        rows = []
    elif node_type == DeleteNode:
        deleted = rows[0]["deleted"] if rows else False
        message = "Registro eliminado" if deleted else "Registro no encontrado"
        rows = []

    # Metadatos espaciales para queries espaciales (usados por el frontend para graficar)
    spatial_meta = None
    if node_type == SelectPointRadiusNode:
        spatial_meta = {
            "type": "radius",
            "point": list(node.point),
            "radius": node.radius,
            "lat_col": None,
            "lon_col": None,
        }
        try:
            t = db.get_table(node.table_name)
            if t.spatial_indexes:
                sp_entry = next(iter(t.spatial_indexes.values()))
                spatial_meta["lat_col"] = sp_entry["columns"][0]
                spatial_meta["lon_col"] = sp_entry["columns"][1]
        except Exception:
            pass
    elif node_type == SelectKNNNode:
        spatial_meta = {
            "type": "knn",
            "point": list(node.point),
            "k": node.k,
            "lat_col": None,
            "lon_col": None,
        }
        try:
            t = db.get_table(node.table_name)
            if t.spatial_indexes:
                sp_entry = next(iter(t.spatial_indexes.values()))
                spatial_meta["lat_col"] = sp_entry["columns"][0]
                spatial_meta["lon_col"] = sp_entry["columns"][1]
        except Exception:
            pass

    op_name = _NODE_OP.get(node_type, "UNKNOWN")
    table = _table_name_from(node)
    _metrics_history.append({
        "operation": op_name,
        "table":     table,
        "reads":     stats["reads"],
        "writes":    stats["writes"],
        "total_io":  stats["reads"] + stats["writes"],
        "time_ms":   stats["time_ms"],
        "row_count": len(rows),
    })

    return {
        "columns":      columns,
        "rows":         rows,
        "row_count":    len(rows),
        "reads":        stats["reads"],
        "writes":       stats["writes"],
        "time_ms":      stats["time_ms"],
        "message":      message,
        "spatial_meta": spatial_meta,
    }


@app.get("/api/v1/tables")
def list_tables():
    tables = []
    for name in db.list_tables():
        table = db.get_table(name)
        tables.append({
            "name": name,
            "columns": table.column_definitions,
            "primary_key": table.schema.primary_key,
            "primary_index_type": table.primary_index_type,
            "data_file": table.index.pm.filepath,
            "secondary_indexes": [
                {"name": index_name, "type": meta["type"], "columns": meta["columns"]}
                for index_name, meta in table.secondary_indexes.items()
            ],
            "spatial_indexes": [
                {"name": index_name, "type": meta["type"], "columns": meta["columns"]}
                for index_name, meta in table.spatial_indexes.items()
            ],
            "content_indexes": [
                {"name": index_name, "type": meta["type"], "columns": meta["columns"]}
                for index_name, meta in table.content_indexes.items()
            ],
        })
    return {"tables": tables, "count": len(tables)}


@app.delete("/api/v1/tables/{name}")
def drop_table(name: str):
    try:
        db.drop_table(name)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"message": f"Tabla '{name}' eliminada", "table": name}


@app.get("/api/v1/indexes/{table}/points")
def get_rtree_points(table: str):
    try:
        t = db.get_table(table)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if not t.spatial_indexes:
        raise HTTPException(status_code=400, detail=f"'{table}' no tiene un índice espacial")
    spatial_index = next(iter(t.spatial_indexes.values()))["index"]
    raw = spatial_index.all_points()
    points = []
    for point in raw:
        record = db.resolve_primary_key(t, point["pk"])
        points.append({"x": point["lon"], "y": point["lat"], "record": record})
    return {"table": table, "points": points, "count": len(points)}


@app.get("/api/v1/metrics/history")
def metrics_history(limit: int = 50):
    entries = list(_metrics_history)[-limit:]
    return {"entries": entries, "count": len(entries)}


@app.delete("/api/v1/metrics")
def clear_metrics():
    _metrics_history.clear()
    return {"message": "Historial de métricas limpiado"}


@app.post("/api/v1/tables/upload")
async def upload_csv_table(
    file: UploadFile = File(...),
    table_name: str = Form(...),
    index_type: str = Form(...),
    fields: str = Form(...),
    secondary_indexes: str = Form(default="[]"),
):
    fields_data = _json.loads(fields)
    sec_indexes_data = _json.loads(secondary_indexes)

    schema_fields = []
    primary_key = fields_data[0]["name"]
    for fd in fields_data:
        if fd.get("primary_key"):
            primary_key = fd["name"]
        ft_str = fd["type"]
        if ft_str == "INT":
            schema_fields.append(Field(fd["name"], FieldType.INT))
        elif ft_str == "REAL":
            schema_fields.append(Field(fd["name"], FieldType.FLOAT))
        elif ft_str == "BOOLEAN":
            schema_fields.append(Field(fd["name"], FieldType.BOOL))
        elif ft_str in ("TEXT", "IMAGE", "AUDIO"):
            schema_fields.append(Field(fd["name"], FieldType.VARCHAR, max_length=int(fd.get("size", 255))))
        else:
            schema_fields.append(Field(fd["name"], FieldType.VARCHAR, max_length=int(fd.get("size", 50))))

    try:
        schema = Schema(schema_fields, primary_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    os.makedirs(DATA_DIR, exist_ok=True)
    csv_path = os.path.join(DATA_DIR, f"{table_name}.csv")
    content = await file.read()
    with open(csv_path, "wb") as f:
        f.write(content)

    try:
        column_definitions = []
        for field in fields_data:
            field_type = field["type"]
            if field_type == "CHAR":
                column_definitions.append({"name": field["name"], "type": "CHAR", "size": int(field["size"])})
            elif field_type in ("TEXT", "IMAGE", "AUDIO"):
                column_definitions.append({"name": field["name"], "type": field_type})
            else:
                column_definitions.append({"name": field["name"], "type": field_type})
        table = db.create_table(table_name, schema, column_definitions, index_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        count = db._load_csv(table, csv_path)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Error cargando CSV: {e}")

    for si in sec_indexes_data:
        try:
            cols = si.get("columns") or [si["column"]]
            index_name = si.get("name", f"idx_{table_name}_{'_'.join(cols)}")
            db.add_secondary_index(table_name, index_name, cols, si["index_type"])
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Error creando indice '{index_name}': {e}")

    return {"message": f"Tabla '{table_name}' creada con {count} registros", "table": table_name, "rows_loaded": count}


# ==================================================================
# Recuperacion multimodal (Proyecto 2)
# ==================================================================

# Herramienta local: el explorador arranca en el HOME del usuario y permite
# navegar cualquier carpeta del equipo (sin restringir la ruta).
_ALLOWED_ROOT = _Path(os.path.expanduser("~")).resolve()
_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
_AUDIO_EXT = {".wav", ".mp3", ".flac", ".ogg", ".au", ".m4a"}
_MEDIA_EXT = _IMAGE_EXT | _AUDIO_EXT


def _within_allowed(path: _Path) -> bool:
    return True


def _find_content_index(table, column: str, kinds=("inverted", "multimedia")):
    for entry in table.content_indexes.values():
        if entry["type"] in kinds and entry["columns"] == [column]:
            return entry
    return None


def _resolve_hits(table, hits, genre_filter=None):
    rows = []
    rank = 0
    for doc_id, score in hits:
        record = db.resolve_primary_key(table, doc_id)
        if record is None:
            continue
        if genre_filter and str(record.get("genero", "")).lower() != genre_filter.lower():
            continue
        rank += 1
        row = dict(record)
        row["_score"] = round(float(score), 6)
        row["_rank"] = rank
        rows.append(row)
    return rows


class TextSearchRequest(BaseModel):
    table: str
    column: str
    query: str
    k: int = 10
    method: str | None = None
    genre: str | None = None


class FolderLoadRequest(BaseModel):
    table: str
    folder: str
    mapping: dict           # columna -> "file_path"|"subfolder"|"filename"|"autoincrement"|"empty"
    limit_per_subfolder: int | None = None
    copy: bool = True        # copia los archivos a back/data/media/<tabla>/ (seguro/portable)


@app.get("/api/v1/fs")
def browse_fs(path: str = ""):
    """Explorador de carpetas para elegir la fuente de datos (navega todo el equipo)."""
    base = _Path(path).resolve() if path else _ALLOWED_ROOT
    if not base.is_dir():
        raise HTTPException(status_code=400, detail=f"No es una carpeta valida: {path or base}")
    try:
        children = sorted(base.iterdir(), key=lambda p: p.name.lower())
    except PermissionError:
        raise HTTPException(status_code=403, detail="Sin permiso para leer esta carpeta")
    dirs, media_count = [], 0
    for child in children:
        try:
            if child.is_dir():
                dirs.append({"name": child.name, "path": str(child)})
            elif child.suffix.lower() in _MEDIA_EXT:
                media_count += 1
        except (PermissionError, OSError):
            continue
    parent = None if base.parent == base else str(base.parent)
    return {"path": str(base), "parent": parent, "dirs": dirs, "media_files": media_count}


@app.get("/api/v1/media")
def serve_media(path: str):
    """Sirve un archivo de imagen/audio del dataset para mostrar/reproducir en el front."""
    target = _Path(path)
    if not _within_allowed(target) or not target.is_file():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return FileResponse(str(target))


@app.get("/api/v1/media/image")
def serve_media_image(path: str):
    return serve_media(path)


@app.post("/api/v1/media/query-image")
async def upload_query_image(file: UploadFile = File(...)):
    ext = _Path(file.filename or "").suffix.lower()
    if ext not in _IMAGE_EXT:
        raise HTTPException(status_code=400, detail="Formato de imagen no soportado")
    query_dir = _Path(DATA_DIR) / "query_images"
    query_dir.mkdir(parents=True, exist_ok=True)
    out = query_dir / f"{uuid4().hex}{ext}"
    out.write_bytes(await file.read())
    return {"path": out.resolve().as_posix()}


@app.post("/api/v1/datasets/load-folder")
def load_folder(req: FolderLoadRequest):
    """Inserta una fila por archivo media de una carpeta, mapeando columnas.

    mapping: por cada columna de la tabla, de donde sale su valor.
    Tipico GTZAN: {"pista":"file_path","genero":"subfolder","id":"autoincrement"}.
    """
    try:
        table = db.get_table(req.table)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    base = _Path(req.folder)
    if not _within_allowed(base) or not base.is_dir():
        raise HTTPException(status_code=400, detail="Carpeta no permitida o inexistente")

    import shutil
    from ..indexes.base_index import DuplicateKeyError
    pk = table.schema.primary_key
    next_id = 1
    inserted = 0

    # Carpeta gestionada por el backend: los archivos se copian aqui para que la
    # coleccion sea auto-contenida (no depende de que el dataset externo siga ahi).
    media_root = _Path(DATA_DIR) / "media" / req.table

    def store_media(f: _Path, subfolder: str) -> str:
        """Devuelve la ruta a usar en la columna: copia al proyecto si copy=True."""
        if not req.copy:
            return str(f.resolve())
        dest_dir = media_root / (subfolder or "_")
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f.name
        if not dest.exists() or dest.stat().st_size == 0:
            try:
                shutil.copy2(str(f), str(dest))
            except OSError:
                return str(f.resolve())
        return str(dest.resolve())

    def media_files():
        subdirs = [d for d in sorted(base.iterdir()) if d.is_dir()]
        if subdirs:
            for sub in subdirs:
                files = sorted(f for f in sub.iterdir() if f.suffix.lower() in _MEDIA_EXT)
                if req.limit_per_subfolder:
                    files = files[: req.limit_per_subfolder]
                for f in files:
                    yield f, sub.name
        else:
            for f in sorted(base.iterdir()):
                if f.suffix.lower() in _MEDIA_EXT:
                    yield f, ""

    for f, subfolder in media_files():
        media_path = store_media(f, subfolder)
        record = {}
        for column, source in req.mapping.items():
            if source == "file_path":
                record[column] = media_path
            elif source == "subfolder":
                record[column] = subfolder
            elif source == "filename":
                record[column] = f.stem
            elif source == "autoincrement":
                record[column] = next_id
            else:
                record[column] = ""
        if pk not in record or source == "":
            record[pk] = next_id
        try:
            table.index.add(record)
        except DuplicateKeyError:
            next_id += 1
            continue
        for sec in table.secondary_indexes.values():
            try:
                col = sec["columns"][0]
                sec["index"].add_ref(record[col], record[pk])
            except DuplicateKeyError:
                pass
        next_id += 1
        inserted += 1

    return {
        "table": req.table,
        "inserted": inserted,
        "copied": req.copy,
        "media_dir": str(media_root) if req.copy else None,
    }


@app.post("/api/v1/search/text")
def search_text(req: TextSearchRequest):
    """Busqueda textual por coseno (operador @@), con filtro opcional por genero."""
    try:
        table = db.get_table(req.table)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    entry = _find_content_index(table, req.column, ("inverted",))
    if entry is None:
        raise HTTPException(status_code=422, detail=f"'{req.column}' no tiene indice INVERTED")
    documents = None
    if req.method == "sequential":
        documents = [
            (rec["record"][table.schema.primary_key],
             entry["retriever"].tokenizer.process(rec["record"].get(req.column) or ""))
            for rec in table.index.iter_record_refs()
        ]
    started = time.perf_counter()
    hits = entry["retriever"].search(req.query, req.k, method=req.method, documents=documents)
    elapsed = (time.perf_counter() - started) * 1000
    return {"rows": _resolve_hits(table, hits, req.genre), "time_ms": round(elapsed, 3)}


@app.post("/api/v1/search/media")
async def search_media(
    file: UploadFile = File(...),
    table: str = Form(...),
    column: str = Form(...),
    k: int = Form(10),
    method: str = Form(None),
    genre: str = Form(None),
):
    """Busqueda por similitud (operador <->): sube imagen/audio -> vecinos mas cercanos."""
    try:
        tbl = db.get_table(table)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    entry = _find_content_index(tbl, column, ("multimedia",))
    if entry is None:
        raise HTTPException(status_code=422, detail=f"'{column}' no tiene indice MULTIMEDIA")

    suffix = _Path(file.filename or "q").suffix or ".bin"
    tmp = _Path(tempfile.gettempdir()) / f"query_{int(time.time()*1000)}{suffix}"
    tmp.write_bytes(await file.read())
    try:
        started = time.perf_counter()
        hits = entry["retriever"].search(str(tmp), k, method=method or None)
        elapsed = (time.perf_counter() - started) * 1000
    finally:
        tmp.unlink(missing_ok=True)
    return {"rows": _resolve_hits(tbl, hits, genre), "time_ms": round(elapsed, 3)}


class ExperimentRequest(BaseModel):
    table: str
    column: str
    kind: str = "media"            # "media" | "text"
    engines: list[str] = ["propio", "secuencial"]
    top_k: int = 10
    queries: int = 20
    repeats: int = 3


def _latency_stats(values: list[float]) -> dict:
    ordered = sorted(values)
    n = len(ordered)
    mean = sum(ordered) / n
    median = ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2
    p95 = ordered[min(n - 1, max(0, round(0.95 * n) - 1))]
    return {"mean_ms": round(mean, 4), "median_ms": round(median, 4), "p95_ms": round(p95, 4)}


@app.post("/api/v1/experiments/run")
def run_experiment(req: ExperimentRequest):
    """Compara motores (propio indexado vs secuencial) sobre las mismas consultas.

    Mide latencia (media/mediana/p95), throughput, precision@k (genero como proxy)
    y tamano de indice. Aisla el ranking: codifica la consulta una vez y cronometra
    solo la busqueda (no la extraccion). Devuelve JSON, sin nada visual.
    """
    from ..retrieval.media.histogram import to_sparse

    try:
        table = db.get_table(req.table)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    kind_to_index = {"media": "multimedia", "text": "inverted"}
    entry = _find_content_index(table, req.column, (kind_to_index.get(req.kind, "multimedia"),))
    if entry is None:
        raise HTTPException(status_code=422, detail=f"'{req.column}' no tiene indice para kind={req.kind}")
    retriever = entry["retriever"]
    pk = table.schema.primary_key

    rows = [item["record"] for item in table.index.iter_record_refs()]
    if not rows:
        raise HTTPException(status_code=422, detail="la tabla no tiene filas")
    genre_of = {r[pk]: r.get("genero") for r in rows}
    step = max(1, len(rows) // req.queries)
    sample = rows[::step][: req.queries]

    method_map = {"propio": None, "secuencial": "sequential"}
    documents = None
    if "secuencial" in req.engines and req.kind == "text":
        documents = [(r[pk], retriever.tokenizer.process(r.get(req.column) or "")) for r in rows]

    # Precodifica cada consulta una sola vez (fuera del cronometro de busqueda).
    encoded = []
    for r in sample:
        qval = r.get(req.column)
        if qval in (None, ""):
            continue
        if req.kind == "media":
            dense = retriever._encode(str(qval))
            encoded.append((r, {"dense": dense, "sparse": to_sparse(dense)}))
        else:
            encoded.append((r, {"terms": retriever.tokenizer.process(str(qval))}))

    results = {}
    for engine in req.engines:
        method = method_map.get(engine)
        latencies, precisions = [], []
        for r, enc in encoded:
            hits = []
            for _ in range(req.repeats):
                t0 = time.perf_counter()
                if req.kind == "media":
                    if method == "sequential":
                        hits = retriever.sequential.knn(enc["dense"], req.top_k)
                    else:
                        hits = retriever.index.knn(enc["sparse"], req.top_k)
                else:
                    if method == "sequential":
                        hits = retriever.ranker.rank_sequential(enc["terms"], req.top_k, documents)
                    else:
                        hits = retriever.ranker.rank(enc["terms"], req.top_k)
                latencies.append((time.perf_counter() - t0) * 1000)
            qgen = r.get("genero")
            if qgen is not None and hits:
                rel = sum(1 for doc_id, _ in hits if genre_of.get(doc_id) == qgen)
                precisions.append(rel / len(hits))
        stats = _latency_stats(latencies)
        results[engine] = {
            **stats,
            "throughput_qps": round(1000 / stats["mean_ms"], 2) if stats["mean_ms"] else None,
            "precision_at_k": round(sum(precisions) / len(precisions), 4) if precisions else None,
            "index_size": entry["retriever"].index.index_size_bytes() if method is None else None,
        }

    return {
        "table": req.table, "column": req.column, "kind": req.kind,
        "top_k": req.top_k, "queries": len(encoded), "repeats": req.repeats,
        "engines": results,
    }
