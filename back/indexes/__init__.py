from .base_index import Index, DuplicateKeyError, NotSupportedError
from .sequential_file import SequentialFile
from .extendible_hashing import ExtendibleHashing
from .bplus_tree import BPlusTree
from .rtree import RTree, InternalNode, LeafNode


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _build_test_schema():
    from ..storage import Schema, Field, FieldType

    return Schema([
        Field("id", FieldType.INT),
        Field("name", FieldType.VARCHAR, max_length=16),
        Field("lat", FieldType.FLOAT),
        Field("lon", FieldType.FLOAT),
    ], primary_key="id")


def _run_rtree_manual_tests() -> None:
    import os
    import shutil
    import uuid
    from ..storage import DiskStats, PageManager

    schema = _build_test_schema()
    refs = [
        {"lat": 0.0, "lon": 0.0, "pk": 11},
        {"lat": 0.0, "lon": 0.01, "pk": 12},
        {"lat": 0.01, "lon": 0.0, "pk": 13},
        {"lat": 1.0, "lon": 1.0, "pk": 20},
    ]

    tmpdir = os.path.join(
        os.path.dirname(__file__),
        "..",
        "data",
        f"_rtree_manual_{uuid.uuid4().hex}",
    )
    os.makedirs(tmpdir, exist_ok=True)

    try:
        filepath = os.path.join(tmpdir, "rtree_test.bin")
        stats = DiskStats()
        pm = PageManager(filepath, stats)
        index = RTree(schema, pm, stats, "lat", "lon")
        index.max_entries = 2
        index.min_entries = 1

        index.build_from_refs(refs)

        root_node = index._read_node(index.root_id)
        _assert(isinstance(root_node, InternalNode), "La raiz debe convertirse en nodo interno tras el split")

        stack = [index.root_id]
        found_leaf = False
        while stack:
            current = index._read_node(stack.pop())
            if isinstance(current, LeafNode):
                found_leaf = True
                continue
            for entry in current.entries:
                stack.append(entry["child"])
        _assert(found_leaf, "El arbol debe contener nodos hoja accesibles desde la raiz")

        found = index.search((0.0, 0.01))
        _assert(
            found == 12,
            "La busqueda exacta debe recuperar la llave primaria correcta",
        )

        radius_results = index.range_search((0.0, 0.0), 2.0)
        _assert(set(radius_results) == {11, 12, 13}, "La busqueda por radio debe recuperar las llaves primarias cercanas esperadas")

        knn_results = index.knn((0.0, 0.0), 2)
        _assert(knn_results[0] == 11, "El vecino mas cercano al origen debe ser la PK del propio punto del origen")
        _assert(set(knn_results) == {11, 12}, "kNN debe devolver las dos llaves primarias mas cercanas esperadas en este conjunto")

        removed = index.remove_ref(12)
        _assert(removed, "La eliminacion por referencia debe reportar exito para un punto existente")
        _assert(index.search((0.0, 0.01)) is None, "El punto eliminado no debe aparecer en una busqueda posterior")

        removed_origin = index.remove_ref(11)
        removed_gamma = index.remove_ref(13)
        removed_delta = index.remove_ref(20)
        _assert(removed_origin and removed_gamma and removed_delta, "El arbol debe poder vaciarse eliminando referencias restantes")
        _assert(index.root_id is None, "La raiz debe contraerse a None cuando el RTree queda vacio")

        rebuilt_refs = refs[:3]
        index.build_from_refs(rebuilt_refs)
        _assert(index.root_id is not None, "build_from_refs debe reconstruir la raiz despues de vaciar el arbol")

        reloaded_stats = DiskStats()
        reloaded_pm = PageManager(filepath, reloaded_stats)
        reloaded_index = RTree(schema, reloaded_pm, reloaded_stats, "lat", "lon")
        persisted = reloaded_index.search((1.0, 1.0))
        _assert(persisted is None, "Los puntos eliminados no deben reaparecer tras recargar el indice")
        persisted = reloaded_index.search((0.01, 0.0))
        _assert(
            persisted == 13,
            "La raiz y los nodos deben recargarse correctamente desde disco",
        )

        underflow_refs = [
            {"lat": 0.0, "lon": 0.0, "pk": 30},
            {"lat": 0.0, "lon": 0.1, "pk": 31},
            {"lat": 5.0, "lon": 5.0, "pk": 40},
            {"lat": 5.1, "lon": 5.1, "pk": 41},
        ]
        underflow_pm = PageManager(os.path.join(tmpdir, "rtree_underflow.bin"), DiskStats())
        underflow_index = RTree(schema, underflow_pm, DiskStats(), "lat", "lon")
        underflow_index.max_entries = 3
        underflow_index.min_entries = 2
        underflow_index.build_from_refs(underflow_refs)
        _assert(underflow_index.remove_ref(30), "La eliminacion debe poder disparar underflow en un subarbol")
        _assert(
            underflow_index.search((0.0, 0.1)) is not None,
            "Las referencias restantes del subarbol eliminado deben reinsertarse correctamente",
        )
        _assert(
            underflow_index.search((5.0, 5.0)) is not None and underflow_index.search((5.1, 5.1)) is not None,
            "La eliminacion con underflow no debe afectar las otras ramas del arbol",
        )

        print("RTREE 9/9 pruebas manuales superadas")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    _run_rtree_manual_tests()
