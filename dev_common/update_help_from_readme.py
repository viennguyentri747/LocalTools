#!/usr/bin/env python3
"""
Update tools' argparse help epilog using examples extracted from README.md.

- Discovers tool scripts in top-level folders matching ".*_tools$" with names starting with "t_" and ending with .py
- Parses README.md code blocks and associates examples to tools by fuzzy match
- Injects examples into each tool by setting `parser.epilog = ...` after the parser is created
- Ensures `parser.formatter_class = argparse.RawTextHelpFormatter` so newlines render correctly

Run:
  python3 dev_common/update_help_from_readme.py
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]


def read_readme() -> Optional[str]:
    p = ROOT / "README.md"
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None


def list_tool_files() -> List[Path]:
    tools: List[Path] = []
    for child in ROOT.iterdir():
        if child.is_dir() and child.name.endswith("_tools"):
            for f in child.iterdir():
                if f.is_file() and f.suffix == ".py" and f.name.startswith("t_"):
                    tools.append(f)
    return sorted(tools)


def find_code_blocks(md: str) -> List[str]:
    blocks: List[str] = []
    fence = "```"
    pos = 0
    while True:
        start = md.find(fence, pos)
        if start == -1:
            break
        lang_end = md.find("\n", start + 3)
        if lang_end == -1:
            break
        end = md.find(fence, lang_end + 1)
        if end == -1:
            break
        block = md[lang_end + 1:end].strip("\n")
        blocks.append(block)
        pos = end + 3
    return blocks


def examples_for_tool(blocks: List[str], tool_path: Path) -> List[str]:
    folder = tool_path.parent.name
    filename = tool_path.name
    stem = tool_path.stem
    stem_no_t = stem[2:] if stem.startswith("t_") else stem
    candidates = [
        f"{folder}/{filename}",
        f"{folder}/{stem}",
        f"{folder}/{stem_no_t}",
        f"{folder}/{stem_no_t}.py",
        filename,
        stem,
        stem_no_t,
        f"{stem_no_t}.py",
    ]
    out: List[str] = []
    for b in blocks:
        if any(c in b for c in candidates):
            out.append(b.strip())
    return out


def inject_epilog(src: str, examples: List[str]) -> Optional[str]:
    # Build epilog only if examples exist
    epilog_text = None
    if examples:
        body = ["Examples:"]
        for i, ex in enumerate(examples, 1):
            body.append(f"\n# Example {i}\n{ex}\n")
        epilog_text = "\n".join(body).rstrip() + "\n"

    # Locate parser assignment: <indent><var> = argparse.ArgumentParser(
    pattern = re.compile(r"^(?P<indent>\s*)(?P<var>\w+)\s*=\s*argparse\.ArgumentParser\(", re.MULTILINE)
    m = pattern.search(src)
    if not m:
        return None
    indent = m.group("indent")
    var = m.group("var")
    # Work in lines to reliably find the closing line
    lines = src.splitlines(keepends=True)
    # Find line index of parser assignment
    start_line_idx = src[:m.start()].count("\n")
    # Find open paren column in that line region
    # Now scan forward lines while counting parens to find the closing line
    depth = 0
    close_line_idx = None
    for idx in range(start_line_idx, len(lines)):
        line = lines[idx]
        # Count parentheses in this line
        for ch in line:
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    close_line_idx = idx
                    break
        if close_line_idx is not None:
            break
    if close_line_idx is None:
        return None

    # Join middle region for cleaning
    before = "".join(lines[:start_line_idx])
    middle_lines = lines[start_line_idx:close_line_idx + 1]
    after = "".join(lines[close_line_idx + 1 :])

    # Global cleanup: remove any existing formatter_class assignment and epilog blocks for this var anywhere
    # Remove epilog triple-quoted blocks
    epilog_block_re = re.compile(rf"^\s*{re.escape(var)}\.epilog\s*=\s*(\"\"\"|''')(?:.|\n)*?\1\s*\n", re.MULTILINE)
    middle = re.sub(epilog_block_re, "", "".join(middle_lines))
    after = re.sub(epilog_block_re, "", after)
    # Remove simple one-line assignments too
    fc_line_re = re.compile(rf"^\s*{re.escape(var)}\.formatter_class\s*=.*\n", re.MULTILINE)
    middle = re.sub(fc_line_re, "", middle)
    after = re.sub(fc_line_re, "", after)

    # Also purge any stray leading triple-quoted block immediately after 'ArgumentParser(' with no keyword
    # Heuristic: if middle starts with something like "...ArgumentParser(\n\s*"""..."""\n"
    # remove that block until the next triple quotes.
    # Heuristic: drop any leading lines after the first that don't look like keyword args
    mid_lines = middle.splitlines(keepends=True)
    if mid_lines:
        cleaned_mid_lines = [mid_lines[0]]
        seen_kw = False
        for ln in mid_lines[1:]:
            s = ln.strip()
            if not seen_kw:
                if ("=" in ln) or s.startswith(")") or s.startswith("description=") or s.startswith("formatter_class="):
                    seen_kw = True
                    cleaned_mid_lines.append(ln)
                else:
                    # drop stray line
                    continue
            else:
                cleaned_mid_lines.append(ln)
        middle = "".join(cleaned_mid_lines)

    # Prepare insertion lines
    insert_lines: List[str] = []
    insert_lines.append(f"{indent}{var}.formatter_class = argparse.RawTextHelpFormatter\n")
    if epilog_text is not None:
        triple = '"""'
        insert_lines.append(f"{indent}{var}.epilog = {triple}{epilog_text}{triple}\n")

    new_src = before + middle + "".join(insert_lines) + after
    return new_src if new_src != src else None


def update_file(path: Path, examples: List[str]) -> bool:
    src = path.read_text(encoding="utf-8", errors="ignore")
    updated = inject_epilog(src, examples)
    if updated is None:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    md = read_readme()
    if not md:
        print("README.md not found or unreadable; nothing to update.")
        return 1
    blocks = find_code_blocks(md)
    tool_files = list_tool_files()
    any_updated = False
    for tool in tool_files:
        ex = examples_for_tool(blocks, tool)
        if not ex:
            continue
        ok = update_file(tool, ex)
        if ok:
            print(f"Updated help epilog in {tool}")
            any_updated = True
    if not any_updated:
        print("No tools matched examples; no files changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
