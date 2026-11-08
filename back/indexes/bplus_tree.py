from .base_index import Index, DuplicateKeyError
from ..storage import Schema, PageManager, DiskStats
import struct
import bisect
import os

class BPlusTree(Index):
    def __init__(self, schema: Schema, page_manager: PageManager, stats: DiskStats, clustered: bool = True):
        super().__init__(schema, page_manager, stats)
        self.schema = schema
        self.page_manager = page_manager
        self.stats = stats
        # clustered=True  → índice primario: registros completos, sin duplicados
        # clustered=False → índice secundario: refs (key, pk), duplicados permitidos
        self.clustered = clustered
        self._root_path = page_manager.filepath.replace(".bin", ".root")
        self._first_leaf_path = page_manager.filepath.replace(".bin", ".first_leaf")
        self.root_id = self._load_root()
        self._first_leaf_id = self._load_first_leaf()
        # Si el archivo está vacío pero el root apunta a una página, resetear
        if self.root_id is not None and self.root_id >= self.page_manager.total_pages():
            self.root_id = None
            self._first_leaf_id = None
            self._save_root()
            self._save_first_leaf()

    def _load_root(self):
        if not os.path.exists(self._root_path):
            return None
        with open(self._root_path, "rb") as f:
            data = f.read(4)
        if len(data) < 4:
            return None
        val = struct.unpack(">i", data)[0]
        return val if val >= 0 else None

    def _save_root(self):
        with open(self._root_path, "wb") as f:
            f.write(struct.pack(">i", self.root_id if self.root_id is not None else -1))

    def _load_first_leaf(self):
        if not os.path.exists(self._first_leaf_path):
            fl = self._leftmost_leaf()
            if fl is not None:
                self._save_first_leaf_raw(fl)
            return fl
        with open(self._first_leaf_path, "rb") as f:
            data = f.read(4)
        if len(data) < 4:
            return None
        val = struct.unpack(">i", data)[0]
        return val if val >= 0 else None

    def _save_first_leaf(self):
        self._save_first_leaf_raw(self._first_leaf_id)

    def _save_first_leaf_raw(self, page_id):
        with open(self._first_leaf_path, "wb") as f:
            f.write(struct.pack(">i", page_id if page_id is not None else -1))

    def search(self, key):
        leaf_id = self._find_leaf(key)
        if leaf_id is None: return None
        node = self._read_node(leaf_id)
        for i, k in enumerate(node["keys"]):
            if k == key: return node["children"][i]
        return None

    def find_record_ref(self, key):
        leaf_id = self._find_leaf(key)
        if leaf_id is None:
            return None
        node = self._read_node(leaf_id)
        for slot, current_key in enumerate(node["keys"]):
            if current_key == key:
                return {"page_id": leaf_id, "slot": slot, "source_id": 0}
        return None

    def add_ref(self, key, primary_key_value) -> None:
        record = {
            self.schema.primary_key: key,
            self.schema.fields[1].name: primary_key_value,
        }
        if self.clustered:
            self.add(record)
        else:
            self._add_unclustered(record)

    def _add_unclustered(self, record) -> None:
        """Inserta en modo no agrupado permitiendo claves duplicadas."""
        key = record[self.schema.primary_key]
        is_first = self.root_id is None
        if is_first:
            self.root_id = self.page_manager.allocate_page()
            self._first_leaf_id = self.root_id
            self._save_root()
            self._save_first_leaf()
            new_node = {"is_leaf": True, "keys": [key], "children": [record], "next_leaf": 0}
            self._write_node(self.root_id, new_node)
            return
        res = self._insert_recursive_unclustered(self.root_id, record)
        if res:
            promoted_key, new_child_id = res
            new_root_id = self.page_manager.allocate_page()
            new_root = {"is_leaf": False, "keys": [promoted_key], "children": [self.root_id, new_child_id]}
            self.root_id = new_root_id
            self._save_root()
            self._write_node(new_root_id, new_root)

    def _insert_recursive_unclustered(self, curr_id, record):
        node = self._read_node(curr_id)
        key = record[self.schema.primary_key]
        if node["is_leaf"]:
            idx = bisect.bisect_right(node["keys"], key)  # permite duplicados
            node["keys"].insert(idx, key)
            node["children"].insert(idx, record)
            if len(node["keys"]) > 3:
                return self._split_leaf(curr_id, node)
            self._write_node(curr_id, node)
            return None
        else:
            idx = bisect.bisect_right(node["keys"], key)
            res = self._insert_recursive_unclustered(node["children"][idx], record)
            if res:
                prom_key, new_id = res
                node["keys"].insert(idx, prom_key)
                node["children"].insert(idx + 1, new_id)
                if len(node["keys"]) > 3:
                    return self._split_internal(curr_id, node)
                self._write_node(curr_id, node)
            return None

    def remove_ref(self, primary_key_value) -> bool:
        """Elimina la referencia cuyo pk_field == primary_key_value."""
        pk_field_name = self.schema.fields[1].name
        for item in self.iter_record_refs():
            if item["record"][pk_field_name] == primary_key_value:
                key = item["record"][self.schema.primary_key]
                return self._remove_unclustered(key, primary_key_value) if not self.clustered else self.remove(key)
        return False

    def _remove_unclustered(self, key, pk_value) -> bool:
        """Elimina la primera entrada con (key, pk_value) en modo no agrupado."""
        pk_field_name = self.schema.fields[1].name
        leaf_id = self._find_leaf(key)
        if leaf_id is None:
            return False
        curr_id = leaf_id
        while curr_id is not None:
            node = self._read_node(curr_id)
            for i, k in enumerate(node["keys"]):
                if k > key:
                    return False
                if k == key and node["children"][i].get(pk_field_name) == pk_value:
                    node["keys"].pop(i)
                    node["children"].pop(i)
                    self._write_node(curr_id, node)
                    return True
            next_p = node.get("next_leaf", 0)
            curr_id = next_p if next_p != 0 else None
        return False

    def read_record_ref(self, page_id: int, slot: int, source_id: int = 0) -> dict:
        node = self._read_node(page_id)
        if not node["is_leaf"]:
            raise ValueError("La referencia apunta a una página interna de BPlusTree")
        if slot < 0 or slot >= len(node["children"]):
            raise ValueError("Slot fuera de rango en BPlusTree")
        return node["children"][slot]

    def iter_record_refs(self):
        if self.root_id is None:
            return
        # Usa el puntero persistente a la primera hoja para evitar recorrer el árbol
        curr_id = self._first_leaf_id if self._first_leaf_id is not None else self._leftmost_leaf()
        while curr_id is not None:
            node = self._read_node(curr_id)
            for slot, record in enumerate(node["children"]):
                yield {"record": record, "page_id": curr_id, "slot": slot, "source_id": 0}
            next_p = node.get("next_leaf", 0)
            curr_id = next_p if next_p != 0 else None

    def add(self, record):
        key = record[self.schema.primary_key]
        is_first = self.root_id is None
        if is_first:
            self.root_id = self.page_manager.allocate_page()
            self._first_leaf_id = self.root_id
            self._save_root()
            self._save_first_leaf()
            new_node = {"is_leaf": True, "keys": [key], "children": [record], "next_leaf": 0}
            self._write_node(self.root_id, new_node)
            return
        res = self._insert_recursive(self.root_id, record)
        if res:
            promoted_key, new_child_id = res
            new_root_id = self.page_manager.allocate_page()
            new_root = {"is_leaf": False, "keys": [promoted_key], "children": [self.root_id, new_child_id]}
            self.root_id = new_root_id
            self._save_root()
            self._write_node(new_root_id, new_root)

    def _insert_recursive(self, curr_id, record):
        node = self._read_node(curr_id)
        key = record[self.schema.primary_key]
        if node["is_leaf"]:
            idx = bisect.bisect_left(node["keys"], key)
            if idx < len(node["keys"]) and node["keys"][idx] == key:
                raise DuplicateKeyError(f"Clave duplicada: {key}")
            node["keys"].insert(idx, key)
            node["children"].insert(idx, record)
            if len(node["keys"]) > 3: return self._split_leaf(curr_id, node)
            else: self._write_node(curr_id, node); return None
        else:
            idx = bisect.bisect_right(node["keys"], key)
            res = self._insert_recursive(node["children"][idx], record)
            if res:
                prom_key, new_id = res
                node["keys"].insert(idx, prom_key)
                node["children"].insert(idx + 1, new_id)
                if len(node["keys"]) > 3: return self._split_internal(curr_id, node)
                else: self._write_node(curr_id, node); return None
            return None

    def range_search(self, begin, end):
        leaf_id = self._find_leaf(begin)
        if leaf_id is None: return []

        results = []
        curr_id = leaf_id
        while curr_id is not None: 
            node = self._read_node(curr_id)
            for i, key in enumerate(node["keys"]):
                if key >= begin and key <= end:
                    results.append(node["children"][i])
                elif key > end:
                    return results
            
            
            next_p = node.get("next_leaf", 0)
            curr_id = next_p if next_p != 0 else None 
        return results

    def remove(self, key) -> bool:
        if self.root_id is None:
            return False
            
        success = self._remove_recursive(None, self.root_id, 0, key)
        
        
        root_node = self._read_node(self.root_id)
        if not root_node["is_leaf"] and len(root_node["keys"]) == 0:
            self.root_id = root_node["children"][0]
            self._save_root()
        return success

    def _remove_recursive(self, parent_id, curr_id, child_idx, key):
        node = self._read_node(curr_id)
        
        if node["is_leaf"]:
            if key not in node["keys"]: return False
            idx = node["keys"].index(key)
            node["keys"].pop(idx)
            node["children"].pop(idx)
            self._write_node(curr_id, node)
        else:
            idx = bisect.bisect_right(node["keys"], key)
            success = self._remove_recursive(curr_id, node["children"][idx], idx, key)
            if not success: return False
            
            
            node = self._read_node(curr_id) 
            
        
        if parent_id is not None and len(node["keys"]) == 0:
            self._handle_underflow(parent_id, curr_id, child_idx)
            
        return True

    def _handle_underflow(self, parent_id, curr_id, child_idx):
        parent = self._read_node(parent_id)
        
        
        if child_idx > 0:
            left_id = parent["children"][child_idx - 1]
            self._merge_nodes(parent_id, left_id, curr_id, child_idx - 1)
        
        elif child_idx < len(parent["children"]) - 1:
            right_id = parent["children"][child_idx + 1]
            self._merge_nodes(parent_id, curr_id, right_id, child_idx)

    def _merge_nodes(self, parent_id, left_id, right_id, parent_key_idx):
        parent = self._read_node(parent_id)
        left = self._read_node(left_id)
        right = self._read_node(right_id)
        
        if left["is_leaf"]:
            left["keys"].extend(right["keys"])
            left["children"].extend(right["children"])
            left["next_leaf"] = right["next_leaf"]
        else:
            
            down_key = parent["keys"].pop(parent_key_idx)
            left["keys"].append(down_key)
            left["keys"].extend(right["keys"])
            left["children"].extend(right["children"])
            
        parent["children"].pop(parent_key_idx + 1)
        if not left["is_leaf"] and parent_key_idx < len(parent["keys"]):
            
            pass 
        elif left["is_leaf"] and parent_key_idx < len(parent["keys"]):
            parent["keys"].pop(parent_key_idx)

        self._write_node(parent_id, parent)
        self._write_node(left_id, left)

    # --- Métodos Internos ---
    def _leftmost_leaf(self):
        if self.root_id is None:
            return None
        curr_id = self.root_id
        while True:
            node = self._read_node(curr_id)
            if node["is_leaf"]:
                return curr_id
            curr_id = node["children"][0]

    def _find_leaf(self, key):
        if self.root_id is None: return None
        curr_id = self.root_id
        while True:
            node = self._read_node(curr_id)
            if node["is_leaf"]: return curr_id
            idx = bisect.bisect_right(node["keys"], key)
            curr_id = node["children"][idx]

    def _split_leaf(self, page_id, node):
        mid = len(node["keys"]) // 2
        promote_key = node["keys"][mid]
        new_page_id = self.page_manager.allocate_page()
        new_node = {"is_leaf": True, "keys": node["keys"][mid:], "children": node["children"][mid:], "next_leaf": node.get("next_leaf", 0)}
        node["keys"], node["children"], node["next_leaf"] = node["keys"][:mid], node["children"][:mid], new_page_id
        self._write_node(page_id, node); self._write_node(new_page_id, new_node)
        return promote_key, new_page_id

    def _split_internal(self, page_id, node):
        mid = len(node["keys"]) // 2
        promote_key = node["keys"][mid]
        new_page_id = self.page_manager.allocate_page()
        new_node = {"is_leaf": False, "keys": node["keys"][mid+1:], "children": node["children"][mid+1:]}
        node["keys"], node["children"] = node["keys"][:mid], node["children"][:mid+1]
        self._write_node(page_id, node); self._write_node(new_page_id, new_node)
        return promote_key, new_page_id

    def _get_pk_field(self): return self.schema._field_map[self.schema.primary_key]

    def _pack_key(self, key):
        f = self._get_pk_field()
        if f.field_type.name == "VARCHAR": return str(key).encode("utf-8")[:f.size].ljust(f.size, b"\x00")
        fmt = ">i" if f.field_type.name == "INT" else ">d" if f.field_type.name == "FLOAT" else ">?"
        return struct.pack(fmt, key)

    def _unpack_key(self, data):
        f = self._get_pk_field()
        if f.field_type.name == "VARCHAR": return data.rstrip(b"\x00").decode("utf-8")
        fmt = ">i" if f.field_type.name == "INT" else ">d" if f.field_type.name == "FLOAT" else ">?"
        return struct.unpack(fmt, data)[0]

    def _write_node(self, page_id, node):
        
        header = struct.pack(">?HI", node["is_leaf"], len(node["keys"]), node.get("next_leaf", 0))
        keys_bin = b"".join(self._pack_key(k) for k in node["keys"])
        children_bin = b"".join(self.schema.serialize(r) for r in node["children"]) if node["is_leaf"] else b"".join(struct.pack(">I", c) for c in node["children"])
        self.page_manager.write_page(page_id, (header + keys_bin + children_bin).ljust(4096, b"\x00"))

    def _read_node(self, page_id):
        raw = self.page_manager.read_page(page_id)
        is_leaf, num_keys, next_leaf = struct.unpack(">?HI", raw[:7])
        pk_size, offset = self._get_pk_field().size, 7
        keys = [self._unpack_key(raw[offset + i*pk_size : offset + (i+1)*pk_size]) for i in range(num_keys)]
        offset += num_keys * pk_size
        children = []
        if is_leaf:
            for _ in range(num_keys):
                children.append(self.schema.deserialize(raw[offset : offset + self.schema.record_size]))
                offset += self.schema.record_size
        else:
            for _ in range(num_keys + 1):
                children.append(struct.unpack(">I", raw[offset:offset+4])[0]); offset += 4
        return {"is_leaf": is_leaf, "keys": keys, "children": children, "next_leaf": next_leaf}
