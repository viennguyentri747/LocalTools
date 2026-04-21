#!/usr/local/bin/local_python
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Dict, List, Sequence


class EUtLogType(Enum):
    PLOG = "P"
    ELOG = "E"
    TLOG = "T"

    def to_log_prefix(self) -> str:
        return self.value

    @classmethod
    def from_log_prefix(cls, prefix: str) -> "EUtLogType | None":
        normalized = prefix.strip().upper()
        for candidate in cls:
            if candidate.value == normalized:
                return candidate
        return None


def normalize_log_paths_map(log_paths_by_type: Dict[EUtLogType, Sequence[str | Path]]) -> Dict[EUtLogType, List[Path]]:
    normalized: Dict[EUtLogType, List[Path]] = {}
    for log_type, raw_paths in log_paths_by_type.items():
        clean_paths: List[Path] = []
        seen: set[Path] = set()
        for raw_path in raw_paths:
            path = raw_path if isinstance(raw_path, Path) else Path(raw_path)
            resolved = path.expanduser().resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            clean_paths.append(resolved)
        normalized[log_type] = sorted(clean_paths)
    return normalized


class TestLogInterface(ABC):
    TEST_NAME: str = ""

    @classmethod
    def get_test_name(cls) -> str:
        return cls.TEST_NAME or cls.__name__

    @classmethod
    @abstractmethod
    def get_target_log_types(cls) -> List[EUtLogType]:
        raise NotImplementedError

    @classmethod
    def getTargetLogTypes(cls) -> List[EUtLogType]:
        return cls.get_target_log_types()

    @classmethod
    @abstractmethod
    def run_test(cls, log_paths_by_type: Dict[EUtLogType, List[Path]]) -> None:
        raise NotImplementedError

    @classmethod
    def runTest(cls, log_paths_by_type: Dict[EUtLogType, List[str]]) -> None:
        normalized_map = normalize_log_paths_map(log_paths_by_type)
        cls.run_test(normalized_map)
