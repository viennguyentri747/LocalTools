
from __future__ import annotations

import ast
import glob
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, Tuple

from dev.dev_common.constants import INSENSE_SDK_REPO_PATH
from dev.dev_common.core_independent_utils import LOG, ELogType

_DEFAULT_HEADER_PATTERN = INSENSE_SDK_REPO_PATH / "InsenseSDK" / "inertial-sense*" / "src" / "data_sets.h"
EnumReplacement = tuple[str, str]
EnumReplacements = tuple[EnumReplacement, ...]


# Cache latest resolved data_sets.h path for this process; avoids repeated glob/version scans.
@lru_cache(maxsize=1)
def get_path_to_inertial_sense_data_set_header() -> Path:
    """
    Return the path to the Inertial Sense SDK data_sets.h header.
    The SDK folder name contains the version (for example inertial-sense-sdk-2.6.0).
    We choose the highest version number available to stay resilient across SDK upgrades.
    """
    matches = sorted(Path(p) for p in glob.glob(str(_DEFAULT_HEADER_PATTERN)))
    if not matches:
        raise FileNotFoundError(f"Unable to find data_sets.h using pattern: {_DEFAULT_HEADER_PATTERN}")

    selected = _pick_latest_sdk_header(matches)
    LOG(f"[IESA] Using Inertial Sense data_sets.h at: {selected}", log_type=ELogType.NORMAL)
    return selected


def _pick_latest_sdk_header(candidates: Iterable[Path]) -> Path:
    def parse_version(path: Path) -> Tuple[int, ...]:
        # Expect any ancestor folder name like inertial-sense-sdk-2.6.0.
        for ancestor in path.parents:
            match = re.search(r"inertial-sense-sdk-([0-9]+(?:\.[0-9]+)*)", ancestor.name)
            if match:
                return tuple(int(part) for part in match.group(1).split("."))
        return tuple()

    best_path: Path = None  # type: ignore
    best_version: Tuple[int, ...] = tuple()
    for path in candidates:
        version = parse_version(path)
        if best_path is None or version > best_version:
            best_path = path
            best_version = version
    return best_path


def get_enum_declaration_from_path(
    enum_name: str,
    header_path: Path | str | None = None,
    enum_replacements: Iterable[EnumReplacement] | None = None,
) -> Dict[str, int]:
    """
    Parse the provided enum from data_sets.h and return a mapping of {name: value}.

    The parser understands simple integer literals and bitwise/arithmetic expressions
    that reference other names within the same enum.
    """
    header = Path(header_path) if header_path else get_path_to_inertial_sense_data_set_header()
    normalized_enum_replacements = _normalize_enum_replacements(enum_replacements)
    return _get_enum_declaration_cached(enum_name, str(header.resolve()), normalized_enum_replacements)


# Unbounded cache keyed by (enum_name, resolved_header_path).
# Fast for repeated enum lookups, but stale until process restart if header content changes.
@lru_cache(maxsize=None)
def _get_enum_declaration_cached(enum_name: str, header_path: str, enum_replacements: EnumReplacements) -> Dict[str, int]:
    content = _read_header_text_cached(header_path)
    enum_name_candidates = _enum_name_candidates(enum_name, enum_replacements)
    body = _extract_enum_body(content, enum_name_candidates, enum_name)
    LOG(f"[IESA] Extracted enum body for {enum_name} in {header_path}:\n{body}", log_type=ELogType.DEBUG)
    values: Dict[str, int] = {}
    for name, expr in _iter_name_value_pairs(body):
        cleaned_expr = _normalize_expression(_strip_casts(expr))
        try:
            value = _evaluate_expression(cleaned_expr, values)
        except Exception as exc:
            raise ValueError(f"Failed to evaluate expression '{expr}' for {name} in {enum_name}") from exc
        values[name] = value
        LOG(f"[IESA] Finish evaluating expression '{expr}' for {name} in {enum_name} -> Result: {value}", log_type=ELogType.DEBUG)
    values_with_aliases = _with_symbol_aliases(values, enum_replacements)
    LOG(f"[IESA] Parsed enum {enum_name} ({len(values_with_aliases)} entries)", log_type=ELogType.DEBUG)
    LOG(f"{ {k: hex(v) if v > 9 else v for k, v in values_with_aliases.items()} }", log_type=ELogType.DEBUG)
    return values_with_aliases


# Unbounded cache of header file text by absolute path.
@lru_cache(maxsize=None)
def _read_header_text_cached(header_path: str) -> str:
    return Path(header_path).read_text()


def _extract_enum_body(content: str, enum_name_candidates: Iterable[str], requested_enum_name: str) -> str:
    for candidate in enum_name_candidates:
        pattern = rf"enum\s+{re.escape(candidate)}\s*\{{(?P<body>.*?)\}}\s*;"
        match = re.search(pattern, content, flags=re.DOTALL)
        if match:
            body = match.group("body")
            return re.sub(r"/\*.*?\*/", "", body, flags=re.DOTALL)  # Drop block comments
    raise ValueError(f"Enum {requested_enum_name} not found in data_sets.h")


def _normalize_enum_replacements(enum_replacements: Iterable[EnumReplacement] | None) -> EnumReplacements:
    if enum_replacements is None:
        return tuple()
    normalized = []
    for src, dst in enum_replacements:
        normalized.append((src, dst))
    return tuple(dict.fromkeys(normalized))


def _enum_name_candidates(enum_name: str, enum_replacements: EnumReplacements) -> Tuple[str, ...]:
    names = [enum_name]
    for src, dst in enum_replacements:
        if src in enum_name:
            names.append(enum_name.replace(src, dst))
    return tuple(dict.fromkeys(names))


def _with_symbol_aliases(values: Dict[str, int], enum_replacements: EnumReplacements) -> Dict[str, int]:
    alias_values = dict(values)
    for name, value in list(values.items()):
        for src, dst in enum_replacements:
            if src not in name:
                continue
            alias_name = name.replace(src, dst)
            if alias_name not in alias_values:
                alias_values[alias_name] = value
    return alias_values


def _iter_name_value_pairs(enum_body: str) -> Iterable[Tuple[str, str]]:
    pattern = r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^,]+)"
    for match in re.finditer(pattern, enum_body):
        name = match.group(1)
        expr = match.group(2).strip()
        expr = expr.split("//", 1)[0].strip()  # Remove inline comments
        if name:  # Skip any empty captures
            yield name, expr


def _strip_casts(expr: str) -> str:
    # Remove casts like (int) or (eDataIDs)
    return re.sub(r"\(\s*[A-Za-z_][A-Za-z0-9_\s\*]*\s*\)", "", expr)


def _normalize_expression(expr: str) -> str:
    """Collapse whitespace so multi-line enum expressions parse correctly."""
    return " ".join(expr.split())


def _evaluate_expression(expr: str, known_values: Dict[str, int]) -> int:
    """Safely evaluate expressions containing ints, names, and bitwise/math ops."""
    def eval_node(node: ast.AST) -> int:
        if isinstance(node, ast.Expression):
            return eval_node(node.body)
        if isinstance(node, ast.Constant):
            return int(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub, ast.Invert)):
            operand = eval_node(node.operand)
            if isinstance(node.op, ast.UAdd):
                return +operand
            if isinstance(node.op, ast.USub):
                return -operand
            return ~operand
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.BitOr, ast.BitAnd, ast.BitXor, ast.LShift, ast.RShift, ast.Add, ast.Sub)):
            left = eval_node(node.left)
            right = eval_node(node.right)
            if isinstance(node.op, ast.BitOr):
                return left | right
            if isinstance(node.op, ast.BitAnd):
                return left & right
            if isinstance(node.op, ast.BitXor):
                return left ^ right
            if isinstance(node.op, ast.LShift):
                return left << right
            if isinstance(node.op, ast.RShift):
                return left >> right
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
        if isinstance(node, ast.Name):
            if node.id in known_values:
                return known_values[node.id]
            raise ValueError(f"Unknown identifier '{node.id}'")
        raise ValueError(f"Unsupported expression element: {ast.dump(node)}")

    parsed = ast.parse(expr, mode="eval")
    return eval_node(parsed)
