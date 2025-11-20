from __future__ import annotations

import fnmatch
import io
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Sequence, Tuple
import tiktoken
from dev_common.constants import LINE_SEPARATOR_NO_ENDLINE
from dev_common.format_utils import beautify_number


@dataclass
class FileEntry:
    """
    Represents a single file that will be ingested.
    The relative_path is always relative to the user's requested root.
    """

    absolute_path: Path
    relative_path: Path

    @property
    def display_name(self) -> str:
        rel = self.relative_path.as_posix()
        return rel if rel else self.absolute_path.name


@dataclass
class TreeNode:
    """Simple tree structure used to render the directory layout."""

    name: str
    is_dir: bool
    children: Dict[str, "TreeNode"] = field(default_factory=dict)


@dataclass
class CustomGitingestResult:
    """Metadata about one ingest run."""

    output_path: Path
    is_directory: bool
    files: List[str]
    file_line_counts: Dict[str, int]
    token_count: int

    @property
    def file_count(self) -> int:
        return len(self.files)

    def summary_text(self, input_path: Path) -> str:
        """
        Produce a short human-readable summary similar to the gitingest CLI output.
        """
        lines = [ f"Analysis complete! Output written to: {self.output_path}", "", "Summary:", ]
        lines.append(f"Directory: {input_path}")
        if self.is_directory:
            lines.append(f"Files analyzed: {self.file_count}")
        else:
            file_label = self.files[0] if self.files else input_path.name
            lines.append(f"File: {file_label}")
            line_count = self.file_line_counts.get(file_label, 0)
            lines.append(f"Lines: {line_count}")

        lines.append("")
        lines.append(f"Estimated tokens: {beautify_number(self.token_count, precision=1)}")
        return "\n".join(lines)


try:
    TOKEN_ENCODER = tiktoken.get_encoding("cl100k_base")
except Exception:
    TOKEN_ENCODER = None


def ingest_path(input_path: Path, output_path: Path, include_patterns: Sequence[str] | None = None, exclude_patterns: Sequence[str] | None = None, ) -> CustomGitingestResult:
    """
    Build a context file for the provided filesystem path (file or directory).
    The output includes a directory tree followed by the contents of each file.
    """
    include_patterns = _normalize_patterns(include_patterns, default_all=True)
    exclude_patterns = _normalize_patterns(exclude_patterns, default_all=False)

    normalized_input = input_path.expanduser()
    resolved_input_path = normalized_input.resolve()
    is_directory = resolved_input_path.is_dir()
    entries: List[FileEntry] = collect_file_entries(resolved_input_path, include_patterns, exclude_patterns)
    if not entries:
        raise ValueError(f"No files matched include/exclude filters for '{input_path}'.")
    
    content, file_line_counts, display_names = _build_output_content(resolved_input_path, entries, is_directory)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")

    return CustomGitingestResult(
        output_path=output_path,
        is_directory=is_directory,
        files=display_names,
        file_line_counts=file_line_counts,
        token_count=_estimate_tokens(content),
    )


def collect_file_entries(path: Path, include_patterns: Sequence[str], exclude_patterns: Sequence[str], ) -> List[FileEntry]:
    """Collect FileEntry items from either a single file or a directory tree.
    """
    if not path.exists():
        raise FileNotFoundError(f"Path does not exist!!: {path}")
    def is_valid(rel_str):
        return _matches_include(rel_str, include_patterns) and not _matches_exclude(rel_str, exclude_patterns)

    entries: List[FileEntry] = []
    if path.is_file():
        if is_valid(path.name):
            entries.append(FileEntry(absolute_path=path, relative_path=Path(path.name)))
    elif path.is_dir():
        for dirpath, dirnames, filenames in os.walk(path):
            rel_dir = Path(dirpath).relative_to(path)
            # Filter + collect files from the current directory
            for filename in sorted(filenames):
                rel_file = rel_dir / filename
                if is_valid(rel_file.as_posix()):
                    entries.append(FileEntry(absolute_path=Path(dirpath) / filename, relative_path=rel_file))

            # Modify dirnames in-place to prevent os.walk from visiting excluded subdirs in next iterations (Navigation support)
            dirnames[:] = sorted([
                dirname for dirname in dirnames
                if not _matches_exclude((rel_dir / dirname).as_posix(), exclude_patterns)
            ])
    else:
        raise ValueError(f"Path is neither a regular file nor directory?: {path}")
    return entries


def _build_output_content(root_path: Path, entries: List[FileEntry], is_directory: bool) -> Tuple[str, Dict[str, int], List[str]]:
    sorted_entries = sorted(entries, key=lambda entry: entry.relative_path.as_posix())
    tree_lines = _build_directory_structure_lines(root_path, sorted_entries, is_directory)

    buffer = io.StringIO()
    buffer.write("Directory structure:\n")
    for line in tree_lines:
        buffer.write(f"{line}\n")
    buffer.write("\n")

    file_line_counts: Dict[str, int] = {}
    display_names: List[str] = []

    for entry in sorted_entries:
        display_name = entry.display_name
        display_names.append(display_name)
        file_content = entry.absolute_path.read_text(encoding="utf-8", errors="replace")
        file_line_counts[display_name] = _count_lines(file_content)

        buffer.write(f"{LINE_SEPARATOR_NO_ENDLINE}\n")
        buffer.write(f"FILE: {display_name}\n")
        buffer.write(f"{LINE_SEPARATOR_NO_ENDLINE}\n")
        buffer.write(file_content)
        if not file_content.endswith("\n"):
            buffer.write("\n")
        buffer.write("\n")

    return buffer.getvalue(), file_line_counts, display_names


def _build_directory_structure_lines(
    root_path: Path, entries: List[FileEntry], is_directory: bool
) -> List[str]:
    if not entries:
        return ["+-- (no files matched the given include/exclude patterns)"]

    if not is_directory:
        return [f"+-- {root_path.name}"]

    tree_root = TreeNode(name="", is_dir=True)
    for entry in entries:
        _add_path_to_tree(tree_root, entry.relative_path.parts)

    root_label = _get_root_display_name(root_path)
    lines = [f"+-- {root_label}/"]
    lines.extend(_render_tree(tree_root, prefix=""))
    return lines


def _add_path_to_tree(node: TreeNode, parts: Tuple[str, ...]) -> None:
    if not parts:
        return

    head, *tail = parts
    child = node.children.get(head)
    is_dir = bool(tail)

    if not child:
        child = TreeNode(name=head, is_dir=is_dir)
        node.children[head] = child
    elif is_dir:
        child.is_dir = True

    if tail:
        _add_path_to_tree(child, tuple(tail))


def _render_tree(node: TreeNode, prefix: str) -> List[str]:
    lines: List[str] = []
    children = sorted(
        node.children.values(),
        key=lambda child: (0 if child.is_dir else 1, child.name.lower()),
    )

    for idx, child in enumerate(children):
        is_last = idx == len(children) - 1
        connector = "`--" if is_last else "|--"
        label = f"{child.name}/" if child.is_dir else child.name
        lines.append(f"{prefix}{connector} {label}")

        if child.children:
            extension = "    " if is_last else "|   "
            lines.extend(_render_tree(child, prefix + extension))

    return lines


def _get_root_display_name(path: Path) -> str:
    if path.name:
        return path.name
    resolved = path.resolve()
    return resolved.name if resolved.name else str(resolved)


def _count_lines(content: str) -> int:
    if not content:
        return 0
    line_count = content.count("\n")
    return line_count if content.endswith("\n") else line_count + 1


def _estimate_tokens(content: str) -> int:
    if TOKEN_ENCODER is None:
        # Reasonable fallback when tiktoken is unavailable.
        return len(content.split())
    return len(TOKEN_ENCODER.encode(content))


def _normalize_patterns(patterns: Sequence[str] | None, default_all: bool) -> List[str]:
    normalized = [p.strip() for p in (patterns or []) if p and p.strip()]
    if not normalized and default_all:
        return ["*"]
    return normalized


def _matches_include(candidate: str, include_patterns: Sequence[str]) -> bool:
    if not include_patterns:
        return True
    return any(_pattern_matches(candidate, pattern) for pattern in include_patterns)


def _matches_exclude(candidate: str, exclude_patterns: Sequence[str]) -> bool:
    if not exclude_patterns:
        return False
    return any(_pattern_matches(candidate, pattern) for pattern in exclude_patterns)


def _pattern_matches(candidate: str, pattern: str) -> bool:
    return fnmatch.fnmatch(candidate, pattern) or pattern in candidate
