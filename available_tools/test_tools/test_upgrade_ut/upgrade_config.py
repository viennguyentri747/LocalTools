#!/usr/local/bin/local_python
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

UPGRADE_TYPE_IESA = "iesa"
UPGRADE_TYPE_BUNDLE = "bundle"
UPGRADE_TYPES = {UPGRADE_TYPE_IESA, UPGRADE_TYPE_BUNDLE}


class UpgradeConfigError(ValueError):
    pass


@dataclass
class UpgradeItemConfig:
    type: str
    path: str
    timeout_secs: Optional[int] = None
    supported_unit_types: List[str] = field(default_factory=list)
    supported_sub_parts: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], index: int) -> "UpgradeItemConfig":
        if not isinstance(data, dict):
            raise UpgradeConfigError(f"upgrade_sequence[{index}] must be an object")
        item_type = str(data.get("type", "")).strip().lower()
        if item_type not in UPGRADE_TYPES:
            raise UpgradeConfigError(f"upgrade_sequence[{index}].type must be one of {sorted(UPGRADE_TYPES)}")
        item_path = str(data.get("path", "")).strip()
        if not item_path:
            raise UpgradeConfigError(f"upgrade_sequence[{index}].path is required")
        timeout_raw = data.get("timeout_secs", data.get("timeout", None))
        timeout_secs = None
        if timeout_raw is not None:
            timeout_secs = max(1, int(timeout_raw))
        supported_unit_types_raw = data.get("supported_unit_types", [])
        supported_sub_parts_raw = data.get("supported_sub_parts", [])
        supported_unit_types = [str(x).strip().lower() for x in supported_unit_types_raw] if isinstance(supported_unit_types_raw, list) else []
        supported_sub_parts = [str(x).strip().upper() for x in supported_sub_parts_raw] if isinstance(supported_sub_parts_raw, list) else []
        supported_unit_types = [x for x in supported_unit_types if x]
        supported_sub_parts = [x for x in supported_sub_parts if x]
        return cls(type=item_type, path=item_path, timeout_secs=timeout_secs, supported_unit_types=supported_unit_types, supported_sub_parts=supported_sub_parts)


@dataclass
class UpgradeTestConfig:
    max_retries_per_upgrade: int = 1
    upgrade_sequence: List[UpgradeItemConfig] = field(default_factory=list)
    upgrade_log_dir_path: Optional[str] = None
    cycles: int = 1
    wait_secs_before_next_upgrade: int = 5

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UpgradeTestConfig":
        if not isinstance(data, dict):
            raise UpgradeConfigError("Invalid JSON root object in config")
        sequence_data = data.get("upgrade_sequence", [])
        sequence: List[UpgradeItemConfig] = []
        if isinstance(sequence_data, list) and sequence_data:
            sequence = [UpgradeItemConfig.from_dict(item, idx) for idx, item in enumerate(sequence_data)]
        else:
            # Backward compatibility for legacy config format.
            bundles_info = data.get("bundles_info", {})
            bundle_paths = bundles_info.get("bundle_paths", []) if isinstance(bundles_info, dict) else []
            for path in bundle_paths if isinstance(bundle_paths, list) else []:
                sequence.append(UpgradeItemConfig(type=UPGRADE_TYPE_BUNDLE, path=str(path)))
            iesas_info = data.get("iesas_info", {})
            iesa_paths = iesas_info.get("iesa_paths", []) if isinstance(iesas_info, dict) else []
            for path in iesa_paths if isinstance(iesa_paths, list) else []:
                sequence.append(UpgradeItemConfig(type=UPGRADE_TYPE_IESA, path=str(path)))
        upgrade_log_dir_path = str(data.get("upgrade_log_dir_path")).strip() if data.get("upgrade_log_dir_path") else None
        if not upgrade_log_dir_path and data.get("upgrade_log_path"):
            upgrade_log_dir_path = str(data.get("upgrade_log_path")).strip()
        max_retries_per_upgrade = 1
        if "max_retries_per_upgrade" in data:
            max_retries_per_upgrade = max(0, int(data.get("max_retries_per_upgrade", 1)))
        elif "max_reboot_retries" in data:
            max_retries_per_upgrade = max(0, int(data.get("max_reboot_retries", 1)))
        else:
            retry_data = data.get("retry", {})
            if isinstance(retry_data, dict):
                max_retries_per_upgrade = max(0, int(retry_data.get("max_reboot_retries", 1)))
        wait_secs_before_next_upgrade = max(0, int(data.get("wait_secs_before_next_upgrade", 5)))
        return cls(max_retries_per_upgrade=max_retries_per_upgrade, upgrade_sequence=sequence, upgrade_log_dir_path=upgrade_log_dir_path, cycles=max(1, int(data.get("cycles", 1))), wait_secs_before_next_upgrade=wait_secs_before_next_upgrade)

    @classmethod
    def load_from_file(cls, config_path: str) -> "UpgradeTestConfig":
        try:
            with open(config_path, "r", encoding="utf-8") as file_obj:
                data = json.load(file_obj)
        except FileNotFoundError as exc:
            raise UpgradeConfigError(f"Config file not found: {config_path}") from exc
        except json.JSONDecodeError as exc:
            raise UpgradeConfigError(f"Invalid JSON in config: {config_path}, error: {exc}") from exc
        return cls.from_dict(data)

    def get_all_upgrade_paths(self) -> List[str]:
        return [item.path for item in self.upgrade_sequence]

    def with_overrides(self, cycles: Optional[int] = None, max_retries_per_upgrade: Optional[int] = None) -> "UpgradeTestConfig":
        if cycles is not None:
            self.cycles = max(1, int(cycles))
        if max_retries_per_upgrade is not None:
            self.max_retries_per_upgrade = max(0, int(max_retries_per_upgrade))
        return self

    def get_sequence_by_type(self, item_type: str) -> List[UpgradeItemConfig]:
        normalized = item_type.strip().lower()
        return [item for item in self.upgrade_sequence if item.type == normalized]


def normalize_paths(paths: List[str], config_path: Optional[str] = None) -> List[str]:
    resolved: List[str] = []
    config_parent = Path(config_path).resolve().parent if config_path else None
    for item in paths:
        curr = Path(item).expanduser()
        curr = (config_parent / curr).resolve() if (not curr.is_absolute() and config_parent) else curr.resolve()
        resolved.append(str(curr))
    return resolved


def normalize_single_path(path: str, config_path: Optional[str] = None) -> str:
    return normalize_paths([path], config_path=config_path)[0]
