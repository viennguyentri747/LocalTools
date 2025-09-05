# Import thefuzz library for fuzzy string matching
from dataclasses import dataclass
import os
from thefuzz import fuzz
from pathlib import Path
from typing import List

@dataclass
class PathSearchConfig:
    search_root: Path = Path.cwd()
    resolve_symlinks: bool = False
    max_results: int = 8

def fuzzy_find_paths(query: str, config: PathSearchConfig) -> List[Path]:
    """
    Recursively finds paths in the root directory that fuzzy-match the query
    using the 'thefuzz' library.

    NOTE: All print/stdout statements have been removed to prevent interference
    with prompt_toolkit's rendering.
    """
    if not query:
        return []

    exclude_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', '.vscode', '.idea', 'dist', 'build'}
    candidates = []
    query_lower = query.lower()

    # Use os.walk for better performance than rglob
    for dirpath, dirnames, filenames in os.walk(config.search_root, followlinks=config.resolve_symlinks):
        # Remove excluded directories from dirnames to prevent traversal
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs and not d.startswith('.')]

        # Skip if current directory is excluded or hidden
        current_parts = Path(dirpath).relative_to(config.search_root).parts
        if any(part in exclude_dirs or (part.startswith('.') and part not in {'.', '..'})
               for part in current_parts):
            continue

        # Process files and directories
        all_items = [(dirpath, name, True) for name in dirnames] + [(dirpath, name, False) for name in filenames]

        for item_dir, name, is_dir in all_items:
            # Early filtering: skip if no common characters
            name_lower = name.lower()
            if not any(c in name_lower for c in query_lower):
                continue

            path = Path(item_dir) / name
            relative_path_str = str(path.relative_to(config.search_root))

            # Quick scoring with early exit
            filename_score = fuzz.WRatio(query, name)
            if filename_score > 80:  # Very good filename match
                final_score = filename_score * 1.1
            else:
                path_score = fuzz.partial_ratio(query, relative_path_str)
                final_score = max(filename_score * 1.1, path_score)

            if final_score > 65:
                candidates.append((final_score, path, relative_path_str))

                # Early termination if we have enough high-quality candidates
                if len(candidates) > config.max_results * 3 and final_score < 80:
                    break

    # Sort and return top results
    candidates.sort(key=lambda x: (-x[0], len(x[2])))
    return [path for score, path, _ in candidates[:config.max_results]]
