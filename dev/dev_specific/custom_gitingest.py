from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Sequence, Tuple, TextIO
import tiktoken
from dev.dev_common.constants import LINE_SEPARATOR_NO_ENDLINE
from dev.dev_common.format_utils import beautify_number
from pathspec.gitignore import GitIgnoreSpec


# --- Tree Rendering Constants (Unicode) ---
TREE_ROOT_FOLDER_ICON = "📁"
TREE_ROOT_FILE_ICON = "📄"
TREE_BRANCH = "├──"
TREE_LAST_BRANCH = "└──"
TREE_VERTICAL_EXTENSION = "│   "
TREE_SPACER_EXTENSION = "    "


@dataclass
class IngestConfig:
    """
    Configuration for the file ingestion process.
    """
    input_path: Path
    output_path: Path
    file_include_patterns: Sequence[str] | None = None  # None = ["*"]
    file_or_folder_exclude_patterns: Sequence[str] | None = None
    ignore_files_in_gitignore: bool = True
    max_file_size_mb: float = 1  # 2 MB ~ 26k lines of code
    skip_binary_files: bool = True

    @property
    def max_file_size_bytes(self) -> int:
        """Convert max file size from MB to bytes."""
        return int(self.max_file_size_mb * 1024 * 1024)

    def __post_init__(self):
        """Normalize paths on initialization."""
        self.input_path = Path(self.input_path).expanduser()
        self.output_path = Path(self.output_path).expanduser()


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


@dataclass(frozen=True)
class GitIgnoreScope:
    """Represents one .gitignore file and the directory it applies to."""
    base_path: Path
    spec: GitIgnoreSpec


@dataclass
class CustomIngestResult:
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
        lines = [
            f"Analysis complete! Output written to: {self.output_path}",
            "",
            "Summary:",
        ]
        lines.append(f"Directory: {input_path}")
        if self.is_directory:
            lines.append(f"Files analyzed: {self.file_count}")
        else:
            file_label = self.files[0] if self.files else input_path.name
            lines.append(f"File: {file_label}")
            line_count = self.file_line_counts.get(file_label, 0)
            lines.append(f"Lines: {line_count}")

        lines.append("")
        lines.append(
            f"Estimated tokens: {beautify_number(self.token_count, precision=1)}"
        )
        return "\n".join(lines)


try:
    TOKEN_ENCODER = tiktoken.get_encoding("cl100k_base")
except Exception:
    TOKEN_ENCODER = None


def run_ingest(config: IngestConfig) -> CustomIngestResult:
    """
    Build a context file for the provided filesystem path (file or directory).
    Streams output directly to disk to avoid MemoryError on large folders.

    Args:
        config: IngestConfig object containing all configuration parameters

    Returns:
        CustomIngestResult with metadata about the ingestion
    """
    include_patterns = _normalize_patterns(config.file_include_patterns, default_all=True)
    exclude_patterns = _normalize_patterns(config.file_or_folder_exclude_patterns, default_all=False)

    resolved_input_path = config.input_path.resolve()
    is_directory = resolved_input_path.is_dir()

    # 1. Collect files (metadata only, no content reading yet)
    entries: List[FileEntry] = collect_file_entries(
        resolved_input_path,
        include_patterns,
        exclude_patterns,
        ignore_files_in_gitignore=config.ignore_files_in_gitignore,
        max_file_size_bytes=config.max_file_size_bytes,
        skip_binary_files=config.skip_binary_files,
    )
    if not entries:
        raise ValueError(f"No files matched include/exclude filters for '{config.input_path}'.")

    # Ensure output directory exists
    config.output_path.parent.mkdir(parents=True, exist_ok=True)

    # 2. Open file once and stream content into it
    file_line_counts: Dict[str, int] = {}
    display_names: List[str] = []
    total_tokens = 0

    with open(config.output_path, "w", encoding="utf-8") as out_f:
        # Write Tree Diagram
        _render_tree_diagram(out_f, resolved_input_path, entries, is_directory)

        # Write Files Content
        for entry in entries:
            display_name = entry.display_name
            display_names.append(display_name)

            # Write Header
            header_str = f"{LINE_SEPARATOR_NO_ENDLINE}\nFILE: {display_name}\n{LINE_SEPARATOR_NO_ENDLINE}\n"
            out_f.write(header_str)
            total_tokens += _estimate_tokens(header_str)

            # Read and Write Content
            try:
                file_content = entry.absolute_path.read_text(encoding="utf-8", errors="replace")

                # Check line ending for safe writing
                if not file_content.endswith("\n"):
                    file_content += "\n"

                out_f.write(file_content)
                out_f.write("\n")  # Extra spacer between files

                # Update stats
                file_line_counts[display_name] = _count_lines(file_content)
                total_tokens += _estimate_tokens(file_content)

            except Exception as e:
                error_msg = f"[Error reading file: {e}]\n"
                out_f.write(error_msg)

    return CustomIngestResult(output_path=config.output_path, is_directory=is_directory, files=display_names, file_line_counts=file_line_counts, token_count=total_tokens, )


def collect_file_entries(
    path: Path,
    file_include_patterns: Sequence[str],
    exclude_patterns: Sequence[str],
    ignore_files_in_gitignore: bool = True,
    max_file_size_bytes: int | None = None,
    skip_binary_files: bool = True,
) -> List[FileEntry]:
    """Collect FileEntry items from either a single file or a directory tree."""
    if not path.exists():
        raise FileNotFoundError(f"Path does not exist, file path = {path}")

    def is_valid_path(file_path: Path, rel_path: Path, gitignore_scopes: Sequence[GitIgnoreScope], is_directory: bool = False, ) -> bool:
        """Check if a file or directory should be processed."""
        rel_path_str = rel_path.as_posix()

        # Check exclude patterns (applies to both files and directories)
        if _matches_exclude(rel_path_str, exclude_patterns):
            path_type = "DIRECTORY" if is_directory else "FILE"
            print(f"SKIP {path_type} REASON: Not match exclude patterns, path = {file_path}")
            return False

        # Check gitignore (applies to both files and directories)
        if gitignore_scopes and _should_git_ignore(rel_path, list(gitignore_scopes), is_dir=is_directory):
            path_type = "FOLDER" if is_directory else "file"
            print(f"SKIP {'DIRECTORY' if is_directory else 'FILE'} REASON: Skipping {path_type} due to .gitignore: {file_path}")
            return False

        # File-specific checks
        if not is_directory:
            # Check size limit
            if max_file_size_bytes is not None:
                try:
                    file_size = file_path.stat().st_size
                    if file_size > max_file_size_bytes:
                        print(
                            f"SKIP FILE REASON: File is large, file path = {file_path}, size = {file_size} > {max_file_size_bytes} bytes)")
                        return False
                except OSError:
                    return False

            # Check if extension is binary
            if skip_binary_files:
                if _is_binary_file(file_path):
                    print(f"SKIP FILE REASON: file is binary, file path = {file_path}")
                    return False

            # Check include patterns (only for files)
            is_included = _matches_include(rel_path_str, file_include_patterns)
            if not is_included:
                print(
                    f"SKIP FILE REASON: Not match include patterns, file path = {file_path}, pattern = {file_include_patterns}")
                return False

        return True

    entries: List[FileEntry] = []
    if path.is_file():
        if is_valid_path(path, Path(path.name), [], is_directory=False):
            entries.append(FileEntry(absolute_path=path, relative_path=Path(path.name)))
    elif path.is_dir():
        gitignore_enabled = ignore_files_in_gitignore

        def walk_directory(
            current_path: Path,
            relative_dir: Path,
            scopes: Sequence[GitIgnoreScope],
        ) -> None:
            updated_scopes: List[GitIgnoreScope] = list(scopes)
            if gitignore_enabled:
                scope: GitIgnoreScope = _load_gitignore_scope(current_path, relative_dir)
                if scope:
                    updated_scopes.append(scope)
            try:
                children = sorted(current_path.iterdir(), key=lambda child: child.name.lower())
            except (FileNotFoundError, PermissionError):
                return

            for child in children:
                rel_child_path = relative_dir / child.name

                if child.is_dir():
                    if child.is_symlink():
                        continue
                    if not is_valid_path(child, rel_child_path, updated_scopes, is_directory=True):
                        continue
                    walk_directory(child, rel_child_path, updated_scopes)
                elif child.is_file():
                    if not is_valid_path(child, rel_child_path, updated_scopes, is_directory=False):
                        continue
                    entries.append(FileEntry(absolute_path=child, relative_path=rel_child_path))

        walk_directory(path, Path(), [])
    else:
        raise ValueError(f"Path is neither a regular file nor directory?: {path}")

    return entries


def _is_binary_file(filepath):
    with open(filepath, 'rb') as f:
        chunk = f.read(8192)  # Read first 8KB
        has_null_byte: bool = b'\x00' in chunk
        return has_null_byte


def _render_tree_diagram(out_f: TextIO, root_path: Path, entries: List[FileEntry], is_directory: bool) -> None:
    """Generates and writes the tree diagram directly to the file object (streaming to file)."""
    out_f.write("DIRECTORY TREE:\n")

    root_label = root_path.name
    if not is_directory:
        out_f.write(f"{TREE_ROOT_FILE_ICON} {root_label}\n")
    else:
        tree_root: TreeNode = TreeNode(name="", is_dir=True)
        for entry in entries:
            _add_path_to_tree_node(tree_root, entry.relative_path.parts)

        out_f.write(f"{TREE_ROOT_FOLDER_ICON} {root_label}/\n")

        # Render recursively returns a list of strings, we write them one by one
        lines = _render_tree_recursively(tree_root, prefix="")
        for line in lines:
            out_f.write(line + "\n")

    out_f.write("\n")  # Spacing after tree


def _add_path_to_tree_node(node: TreeNode, parts: Tuple[str, ...]) -> None:
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
        _add_path_to_tree_node(child, tuple(tail))


def _render_tree_recursively(node: TreeNode, prefix: str) -> List[str]:
    lines: List[str] = []
    children = sorted(
        node.children.values(),
        key=lambda child: (0 if child.is_dir else 1, child.name.lower()),
    )

    for idx, child in enumerate(children):
        is_last = idx == len(children) - 1
        connector = TREE_LAST_BRANCH if is_last else TREE_BRANCH
        label = f"{child.name}/" if child.is_dir else child.name
        lines.append(f"{prefix}{connector} {label}")

        if child.children:
            extension = TREE_SPACER_EXTENSION if is_last else TREE_VERTICAL_EXTENSION
            lines.extend(_render_tree_recursively(child, prefix + extension))

    return lines


def _count_lines(content: str) -> int:
    if not content:
        return 0
    line_count = content.count("\n")
    return line_count if content.endswith("\n") else line_count + 1


def _estimate_tokens(content: str) -> int:
    if TOKEN_ENCODER is None:
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


def _load_gitignore_scope(directory: Path, relative_dir: Path) -> GitIgnoreScope | None:
    gitignore_path = directory / ".gitignore"
    if not gitignore_path.is_file():
        return None

    try:
        with gitignore_path.open("r", encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError:
        return None

    spec = GitIgnoreSpec.from_lines(lines)
    if not spec.patterns:
        return None

    return GitIgnoreScope(base_path=relative_dir, spec=spec)


def _should_git_ignore(relative_path: Path, scopes: List[GitIgnoreScope], is_dir: bool) -> bool:
    if not scopes:
        return False

    ignore_state = False
    matched = False
    for scope in scopes:
        scoped_rel = _relative_to_scope(relative_path, scope.base_path)
        if scoped_rel is None:
            continue

        match_target = _format_scope_relative(scoped_rel, is_dir)
        if match_target is None:
            continue

        include, _ = scope.spec._match_file(enumerate(scope.spec.patterns), match_target)
        if include is None:
            continue

        ignore_state = bool(include)
        matched = True

    return matched and ignore_state


def _relative_to_scope(relative_path: Path, base_path: Path) -> Path | None:
    try:
        return relative_path.relative_to(base_path)
    except ValueError:
        # For the repository root Path(), relative_to succeeds; other mismatches should be ignored.
        if base_path == Path():
            return relative_path
        return None


def _format_scope_relative(scoped_rel: Path, is_dir: bool) -> str | None:
    scoped_str = scoped_rel.as_posix()
    if not scoped_str or scoped_str == ".":
        scoped_str = ""
    if not scoped_str:
        return None
    if is_dir and not scoped_str.endswith("/"):
        return f"{scoped_str}/"
    return scoped_str
