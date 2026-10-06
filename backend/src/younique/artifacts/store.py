from __future__ import annotations


class ObjectStore:
    def __init__(self) -> None:
        self._objects: dict[tuple[str, str], bytes] = {}

    def put(self, bucket: str, key: str, data: bytes) -> None:
        self._objects[(bucket, key)] = data

    def get(self, bucket: str, key: str) -> bytes:
        found = self._objects.get((bucket, key))
        if found is None:
            raise KeyError(key)
        return found

    def delete(self, bucket: str, key: str) -> None:
        self._objects.pop((bucket, key), None)

    def copy(self, src_bucket: str, src_key: str, dst_bucket: str, dst_key: str) -> None:
        self.put(dst_bucket, dst_key, self.get(src_bucket, src_key))

    def contains(self, bucket: str, key: str) -> bool:
        return (bucket, key) in self._objects


_store = ObjectStore()


def get_store() -> ObjectStore:
    return _store


def reset_store() -> None:
    global _store
    _store = ObjectStore()
