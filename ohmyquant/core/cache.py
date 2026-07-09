"""缓存工具

提供内存 LRU 缓存和磁盘缓存，用于加速数据加载和因子计算。
"""
from __future__ import annotations

import hashlib
import pickle
import threading
from collections import OrderedDict
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from .logging import get_logger

logger = get_logger(__name__)


class LRUCache:
    """线程安全的 LRU 缓存"""

    def __init__(self, maxsize: int = 128):
        self.maxsize = maxsize
        self._data: OrderedDict[Any, Any] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: Any) -> Any:
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
                return self._data[key]
            return None

    def set(self, key: Any, value: Any) -> None:
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
            self._data[key] = value
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)

    def has(self, key: Any) -> bool:
        with self._lock:
            return key in self._data

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

    def __contains__(self, key: Any) -> bool:
        return self.has(key)


class DiskCache:
    """磁盘缓存（pickle 序列化）

    用于缓存大数据集（如因子矩阵），避免重复计算。
    """

    def __init__(self, cache_dir: str | Path, max_size_mb: int = 1024):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_size_mb = max_size_mb
        self._lock = threading.Lock()

    def _key_to_path(self, key: str) -> Path:
        key_hash = hashlib.md5(key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{key_hash}.pkl"

    def get(self, key: str) -> Any:
        path = self._key_to_path(key)
        if not path.exists():
            return None
        try:
            with open(path, "rb") as f:
                return pickle.load(f)
        except Exception as e:
            logger.warning(f"读取缓存失败 {key}: {e}")
            path.unlink(missing_ok=True)
            return None

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            path = self._key_to_path(key)
            try:
                with open(path, "wb") as f:
                    pickle.dump(value, f, protocol=pickle.HIGHEST_PROTOCOL)
            except Exception as e:
                logger.warning(f"写入缓存失败 {key}: {e}")
            self._evict()

    def has(self, key: str) -> bool:
        return self._key_to_path(key).exists()

    def clear(self) -> None:
        with self._lock:
            for f in self.cache_dir.glob("*.pkl"):
                f.unlink(missing_ok=True)

    def _evict(self) -> None:
        """LRU 淘汰：超过容量时删除最旧的文件"""
        files = sorted(self.cache_dir.glob("*.pkl"), key=lambda f: f.stat().st_mtime)
        total = sum(f.stat().st_size for f in files)
        while total > self.max_size_mb * 1024 * 1024 and files:
            oldest = files.pop(0)
            total -= oldest.stat().st_size
            oldest.unlink(missing_ok=True)
            logger.debug(f"缓存淘汰: {oldest.name}")


def cached(
    cache: LRUCache | DiskCache,
    key_fn: Callable[..., str] | None = None,
) -> Callable:
    """装饰器：缓存函数返回值

    Args:
        cache: 缓存实例
        key_fn: 自定义 key 生成函数，None 则用参数的 hash
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            if key_fn is not None:
                key = key_fn(*args, **kwargs)
            else:
                kw_tuple = tuple(sorted(kwargs.items()))
                key = f"{func.__name__}:{hash((args, kw_tuple))}"

            cached_val = cache.get(key)
            if cached_val is not None:
                logger.debug(f"缓存命中: {key}")
                return cached_val

            result = func(*args, **kwargs)
            cache.set(key, result)
            return result

        return wrapper

    return decorator


__all__ = ["LRUCache", "DiskCache", "cached"]
