import heapq
import math
import os
import struct
from typing import TypedDict
from .base_index import Index
from ..storage import Schema, PageManager, DiskStats, FieldType


class LeafEntry(TypedDict):
    lat: float
    lon: float
    pk: object


class InternalEntry(TypedDict):
    mbr: tuple
    child: int


_HDR = struct.Struct(">?H")
_MBR = struct.Struct(">dddd")
_CID = struct.Struct(">I")
_PT = struct.Struct(">dd")
PAGE_SIZE = 4096


class RTreeNode:
    def __init__(self, entries: list[dict]):
        self.entries = entries

    @property
    def is_leaf(self) -> bool:
        raise NotImplementedError

    @property
    def count(self) -> int:
        return len(self.entries)

    @property
    def is_empty(self) -> bool:
        return len(self.entries) == 0

    def compute_mbr(self) -> tuple:
        raise NotImplementedError


class InternalNode(RTreeNode):
    @property
    def is_leaf(self) -> bool:
        return False

    def compute_mbr(self) -> tuple:
        if not self.entries:
            return (0.0, 0.0, 0.0, 0.0)
        return (
            min(entry["mbr"][0] for entry in self.entries),
            min(entry["mbr"][1] for entry in self.entries),
            max(entry["mbr"][2] for entry in self.entries),
            max(entry["mbr"][3] for entry in self.entries),
        )


class LeafNode(RTreeNode):
    @property
    def is_leaf(self) -> bool:
        return True

    def compute_mbr(self) -> tuple:
        if not self.entries:
            return (0.0, 0.0, 0.0, 0.0)
        lats = [entry["lat"] for entry in self.entries]
        lons = [entry["lon"] for entry in self.entries]
        return (min(lats), min(lons), max(lats), max(lons))


class RTree(Index):
    def __init__(self, schema: Schema, page_manager: PageManager, stats: DiskStats, lat_field: str, lon_field: str):
        super().__init__(schema, page_manager, stats)
        self.lat_field = lat_field
        self.lon_field = lon_field
        self.pk_field = schema.get_field(schema.primary_key)
        self.pk_size = self.pk_field.size
        self._root_path = page_manager.filepath.replace(".bin", ".root")
        self.root_id = self._load_root()
        leaf_entry_size = _PT.size + self.pk_size
        self.max_entries = min(
            (PAGE_SIZE - _HDR.size) // (_MBR.size + _CID.size),
            (PAGE_SIZE - _HDR.size) // leaf_entry_size,
            50,
        )
        self.min_entries = max(1, self.max_entries // 2)
        if self.root_id is not None and self.root_id >= self.pm.total_pages():
            self.root_id = None
            self._save_root()

    def _load_root(self):
        if not os.path.exists(self._root_path):
            return None
        with open(self._root_path, "rb") as handle:
            data = handle.read(4)
        if len(data) < 4:
            return None
        value = struct.unpack(">i", data)[0]
        return value if value >= 0 else None

    def _save_root(self):
        with open(self._root_path, "wb") as handle:
            handle.write(struct.pack(">i", self.root_id if self.root_id is not None else -1))

    def _pack_pk(self, key) -> bytes:
        if self.pk_field.field_type == FieldType.VARCHAR:
            return str(key).encode("utf-8")[: self.pk_size].ljust(self.pk_size, b"\x00")
        if self.pk_field.field_type == FieldType.INT:
            return struct.pack(">i", int(key))
        if self.pk_field.field_type == FieldType.FLOAT:
            return struct.pack(">d", float(key))
        return struct.pack(">?", bool(key))

    def _unpack_pk(self, raw: bytes):
        if self.pk_field.field_type == FieldType.VARCHAR:
            return raw.rstrip(b"\x00").decode("utf-8")
        if self.pk_field.field_type == FieldType.INT:
            return struct.unpack(">i", raw)[0]
        if self.pk_field.field_type == FieldType.FLOAT:
            return struct.unpack(">d", raw)[0]
        return struct.unpack(">?", raw)[0]

    def add(self, record: dict) -> None:
        self.add_ref(float(record[self.lat_field]), float(record[self.lon_field]), record[self.schema.primary_key])

    def add_ref(self, lat: float, lon: float, primary_key_value) -> None:
        self._insert_leaf_entry({
            "lat": float(lat),
            "lon": float(lon),
            "pk": primary_key_value,
        })

    def build_from_refs(self, entries: list[dict]) -> None:
        self.root_id = None
        self._save_root()
        self.pm.delete_file()
        self.pm._ensure_file()
        for entry in entries:
            self._insert_leaf_entry({
                "lat": float(entry["lat"]),
                "lon": float(entry["lon"]),
                "pk": entry["pk"],
            })

    def _insert_leaf_entry(self, leaf_entry: LeafEntry) -> None:
        if self.root_id is None:
            self.root_id = self.pm.allocate_page()
            self._save_root()
            self._write_node(self.root_id, LeafNode([]))
        path, leaf_id = self._choose_leaf((leaf_entry["lat"], leaf_entry["lon"]))
        leaf = self._read_node(leaf_id)
        leaf.entries.append(leaf_entry)
        if leaf.count > self.max_entries:
            left, right = self._split_node(leaf)
            self._write_node(leaf_id, left)
            new_id = self.pm.allocate_page()
            self._write_node(new_id, right)
            self._adjust_tree(path, leaf_id, new_id)
        else:
            self._write_node(leaf_id, leaf)
            self._adjust_tree(path, leaf_id)

    def search(self, key: tuple):
        if self.root_id is None:
            return None
        lat, lon = float(key[0]), float(key[1])
        stack = [self.root_id]
        while stack:
            node = self._read_node(stack.pop())
            if node.is_leaf:
                for entry in node.entries:
                    if entry["lat"] == lat and entry["lon"] == lon:
                        return entry["pk"]
            else:
                for entry in node.entries:
                    mbr = entry["mbr"]
                    if mbr[0] <= lat <= mbr[2] and mbr[1] <= lon <= mbr[3]:
                        stack.append(entry["child"])
        return None

    def range_search(self, point: tuple, radius: float) -> list:
        if self.root_id is None:
            return []
        results = []
        stack = [self.root_id]
        while stack:
            node = self._read_node(stack.pop())
            if node.is_leaf:
                for entry in node.entries:
                    if self._haversine(point, (entry["lat"], entry["lon"])) <= radius:
                        results.append(entry["pk"])
            else:
                for entry in node.entries:
                    if self._mbr_intersects_circle(entry["mbr"], point, radius):
                        stack.append(entry["child"])
        return results

    def knn(self, point: tuple, k: int) -> list:
        if self.root_id is None:
            return []
        pk_store = []
        heap = [(0.0, 0, False, self.root_id)]
        counter = 1
        results = []
        while heap and len(results) < k:
            _, _, is_pk, data = heapq.heappop(heap)
            if is_pk:
                results.append(pk_store[data])
                continue
            node = self._read_node(data)
            if node.is_leaf:
                for entry in node.entries:
                    dist = self._haversine(point, (entry["lat"], entry["lon"]))
                    idx = len(pk_store)
                    pk_store.append(entry["pk"])
                    heapq.heappush(heap, (dist, counter, True, idx))
                    counter += 1
            else:
                for entry in node.entries:
                    mbr = entry["mbr"]
                    clamp_lat = max(mbr[0], min(point[0], mbr[2]))
                    clamp_lon = max(mbr[1], min(point[1], mbr[3]))
                    dist = self._haversine(point, (clamp_lat, clamp_lon))
                    heapq.heappush(heap, (dist, counter, False, entry["child"]))
                    counter += 1
        return results

    def remove(self, key: tuple) -> bool:
        if self.root_id is None:
            return False
        removed, orphaned, _ = self._remove_by_predicate(
            self.root_id,
            lambda entry: entry["lat"] == float(key[0]) and entry["lon"] == float(key[1]),
            is_root=True,
        )
        if orphaned:
            self._reinsert_leaf_entries(orphaned)
        if removed:
            self._normalize_root()
        return removed

    def remove_ref(self, primary_key_value) -> bool:
        if self.root_id is None:
            return False
        removed, orphaned, _ = self._remove_by_predicate(
            self.root_id,
            lambda entry: entry["pk"] == primary_key_value,
            is_root=True,
        )
        if orphaned:
            self._reinsert_leaf_entries(orphaned)
        if removed:
            self._normalize_root()
        return removed

    def all_points(self) -> list[dict]:
        if self.root_id is None:
            return []
        results = []
        stack = [self.root_id]
        while stack:
            node = self._read_node(stack.pop())
            if node.is_leaf:
                for entry in node.entries:
                    results.append({"lat": entry["lat"], "lon": entry["lon"], "pk": entry["pk"]})
            else:
                for entry in node.entries:
                    stack.append(entry["child"])
        return results

    def _haversine(self, p1: tuple, p2: tuple) -> float:
        lat1, lon1 = math.radians(p1[0]), math.radians(p1[1])
        lat2, lon2 = math.radians(p2[0]), math.radians(p2[1])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return 6371.0 * 2 * math.asin(math.sqrt(min(1.0, value)))

    def _mbr_intersects_circle(self, mbr: tuple, point: tuple, radius: float) -> bool:
        clamp_lat = max(mbr[0], min(point[0], mbr[2]))
        clamp_lon = max(mbr[1], min(point[1], mbr[3]))
        return self._haversine(point, (clamp_lat, clamp_lon)) <= radius

    def _entry_mbr(self, entry: dict, is_leaf: bool) -> tuple:
        if is_leaf:
            return (entry["lat"], entry["lon"], entry["lat"], entry["lon"])
        return entry["mbr"]

    def _merge_mbr(self, left: tuple, right: tuple) -> tuple:
        return (
            min(left[0], right[0]),
            min(left[1], right[1]),
            max(left[2], right[2]),
            max(left[3], right[3]),
        )

    def _entries_mbr(self, entries: list, is_leaf: bool) -> tuple:
        mbr = self._entry_mbr(entries[0], is_leaf)
        for entry in entries[1:]:
            mbr = self._merge_mbr(mbr, self._entry_mbr(entry, is_leaf))
        return mbr

    def _mbr_area(self, mbr: tuple) -> float:
        return max(0.0, (mbr[2] - mbr[0]) * (mbr[3] - mbr[1]))

    def _pick_split_seeds(self, entries: list, is_leaf: bool) -> tuple[int, int]:
        best_pair = (0, 1)
        best_waste = float("-inf")
        for left_idx in range(len(entries) - 1):
            left_mbr = self._entry_mbr(entries[left_idx], is_leaf)
            for right_idx in range(left_idx + 1, len(entries)):
                right_mbr = self._entry_mbr(entries[right_idx], is_leaf)
                merged = self._merge_mbr(left_mbr, right_mbr)
                waste = self._mbr_area(merged) - self._mbr_area(left_mbr) - self._mbr_area(right_mbr)
                if waste > best_waste:
                    best_waste = waste
                    best_pair = (left_idx, right_idx)
        return best_pair

    def _split_node(self, node: RTreeNode) -> tuple:
        entries = list(node.entries)
        if len(entries) <= 1:
            if node.is_leaf:
                return LeafNode(entries), LeafNode([])
            return InternalNode(entries), InternalNode([])

        seed_a, seed_b = self._pick_split_seeds(entries, node.is_leaf)
        left_entries = [entries.pop(seed_a)]
        seed_b = seed_b - 1 if seed_b > seed_a else seed_b
        right_entries = [entries.pop(seed_b)]

        while entries:
            if len(left_entries) + len(entries) == self.min_entries:
                left_entries.extend(entries)
                break
            if len(right_entries) + len(entries) == self.min_entries:
                right_entries.extend(entries)
                break

            left_mbr = self._entries_mbr(left_entries, node.is_leaf)
            right_mbr = self._entries_mbr(right_entries, node.is_leaf)
            best_idx = 0
            best_diff = float("-inf")
            best_left_expand = 0.0
            best_right_expand = 0.0

            for idx, entry in enumerate(entries):
                entry_mbr = self._entry_mbr(entry, node.is_leaf)
                left_expand = self._mbr_area(self._merge_mbr(left_mbr, entry_mbr)) - self._mbr_area(left_mbr)
                right_expand = self._mbr_area(self._merge_mbr(right_mbr, entry_mbr)) - self._mbr_area(right_mbr)
                diff = abs(left_expand - right_expand)
                if diff > best_diff:
                    best_idx = idx
                    best_diff = diff
                    best_left_expand = left_expand
                    best_right_expand = right_expand

            entry = entries.pop(best_idx)
            target = left_entries
            if best_right_expand < best_left_expand:
                target = right_entries
            elif best_left_expand == best_right_expand:
                left_area = self._mbr_area(left_mbr)
                right_area = self._mbr_area(right_mbr)
                if right_area < left_area or (right_area == left_area and len(right_entries) < len(left_entries)):
                    target = right_entries
            target.append(entry)

        if node.is_leaf:
            return LeafNode(left_entries), LeafNode(right_entries)
        return InternalNode(left_entries), InternalNode(right_entries)

    def _choose_leaf(self, point: tuple) -> tuple:
        curr_id = self.root_id
        path = []
        while True:
            node = self._read_node(curr_id)
            if node.is_leaf:
                return path, curr_id
            best_idx = 0
            best_enlargement = float("inf")
            best_area = float("inf")
            for idx, entry in enumerate(node.entries):
                mbr = entry["mbr"]
                new_mbr = (min(mbr[0], point[0]), min(mbr[1], point[1]), max(mbr[2], point[0]), max(mbr[3], point[1]))
                old_area = self._mbr_area(mbr)
                new_area = self._mbr_area(new_mbr)
                enlargement = new_area - old_area
                if enlargement < best_enlargement or (enlargement == best_enlargement and old_area < best_area):
                    best_enlargement = enlargement
                    best_area = old_area
                    best_idx = idx
            path.append((curr_id, best_idx))
            curr_id = node.entries[best_idx]["child"]

    def _adjust_tree(self, path: list, curr_id: int, new_id: int = None) -> None:
        curr_new_id = new_id
        for parent_id, child_idx in reversed(path):
            parent = self._read_node(parent_id)
            curr_node = self._read_node(curr_id)
            parent.entries[child_idx]["mbr"] = curr_node.compute_mbr()
            if curr_new_id is not None:
                new_node = self._read_node(curr_new_id)
                parent.entries.insert(child_idx + 1, {"mbr": new_node.compute_mbr(), "child": curr_new_id})
                if parent.count > self.max_entries:
                    left, right = self._split_node(parent)
                    self._write_node(parent_id, left)
                    split_id = self.pm.allocate_page()
                    self._write_node(split_id, right)
                    curr_id, curr_new_id = parent_id, split_id
                else:
                    self._write_node(parent_id, parent)
                    curr_new_id = None
            else:
                self._write_node(parent_id, parent)
            curr_id = parent_id
        if curr_new_id is not None:
            left_node = self._read_node(curr_id)
            right_node = self._read_node(curr_new_id)
            new_root_id = self.pm.allocate_page()
            self._write_node(new_root_id, InternalNode([
                {"mbr": left_node.compute_mbr(), "child": curr_id},
                {"mbr": right_node.compute_mbr(), "child": curr_new_id},
            ]))
            self.root_id = new_root_id
            self._save_root()

    def _read_node(self, page_id: int) -> RTreeNode:
        raw = self.pm.read_page(page_id)
        is_leaf, num_entries = _HDR.unpack(raw[:_HDR.size])
        offset = _HDR.size
        entries = []
        if is_leaf:
            for _ in range(num_entries):
                lat, lon = _PT.unpack(raw[offset:offset + _PT.size])
                offset += _PT.size
                pk = self._unpack_pk(raw[offset:offset + self.pk_size])
                offset += self.pk_size
                entries.append({"lat": lat, "lon": lon, "pk": pk})
            return LeafNode(entries)
        for _ in range(num_entries):
            mbr = _MBR.unpack(raw[offset:offset + _MBR.size])
            offset += _MBR.size
            child = _CID.unpack(raw[offset:offset + _CID.size])[0]
            offset += _CID.size
            entries.append({"mbr": mbr, "child": child})
        return InternalNode(entries)

    def _write_node(self, page_id: int, node: RTreeNode) -> None:
        data = bytearray(_HDR.pack(node.is_leaf, len(node.entries)))
        if node.is_leaf:
            for entry in node.entries:
                data += _PT.pack(entry["lat"], entry["lon"])
                data += self._pack_pk(entry["pk"])
        else:
            for entry in node.entries:
                data += _MBR.pack(*entry["mbr"])
                data += _CID.pack(entry["child"])
        self.pm.write_page(page_id, bytes(data).ljust(PAGE_SIZE, b"\x00"))

    def _collect_leaf_entries(self, node_id: int) -> list[LeafEntry]:
        node = self._read_node(node_id)
        if node.is_leaf:
            return list(node.entries)
        collected = []
        for entry in node.entries:
            collected.extend(self._collect_leaf_entries(entry["child"]))
        return collected

    def _reinsert_leaf_entries(self, entries: list[LeafEntry]) -> None:
        for entry in entries:
            self._insert_leaf_entry(entry)

    def _remove_by_predicate(self, node_id: int, predicate, is_root: bool = False) -> tuple[bool, list[LeafEntry], bool]:
        node = self._read_node(node_id)
        if node.is_leaf:
            for idx, entry in enumerate(node.entries):
                if predicate(entry):
                    node.entries.pop(idx)
                    self._write_node(node_id, node)
                    if not is_root and 0 < node.count < self.min_entries:
                        orphaned = list(node.entries)
                        node.entries = []
                        self._write_node(node_id, node)
                        return True, orphaned, True
                    return True, [], (not is_root and node.is_empty)
            return False, [], False

        for entry in list(node.entries):
            removed, orphaned, prune_child = self._remove_by_predicate(entry["child"], predicate, False)
            if removed:
                if prune_child:
                    node.entries = [current for current in node.entries if current["child"] != entry["child"]]
                else:
                    child_node = self._read_node(entry["child"])
                    entry["mbr"] = child_node.compute_mbr()
                self._write_node(node_id, node)
                if not is_root and 0 < node.count < self.min_entries:
                    orphaned.extend(self._collect_leaf_entries(node_id))
                    node.entries = []
                    self._write_node(node_id, node)
                    return True, orphaned, True
                return True, orphaned, (not is_root and node.is_empty)
        return False, [], False

    def _normalize_root(self) -> None:
        while self.root_id is not None:
            root = self._read_node(self.root_id)
            if root.is_leaf:
                if root.is_empty:
                    self.root_id = None
                    self._save_root()
                return
            if root.is_empty:
                self.root_id = None
                self._save_root()
                return
            if root.count == 1:
                self.root_id = root.entries[0]["child"]
                self._save_root()
                continue
            return
