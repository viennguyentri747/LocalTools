#!/usr/bin/env python3
"""Fast recursive archive extraction utility."""

from __future__ import annotations

import argparse
import bz2
from contextlib import ExitStack
from dataclasses import dataclass
import gzip
import lzma
import multiprocessing
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
import zipfile

ARCHIVE_SUFFIXES: tuple[str, ...] = (
    ".tar.gz", ".tar.bz2", ".tar.xz", ".tar.zst",
    ".tgz", ".tbz2", ".txz",
    ".tar", ".zip", ".gz", ".bz2", ".xz", ".zst", ".7z", ".rar",
)
TAR_SUFFIXES: tuple[str, ...] = (".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz", ".tar")


def detect_archive_suffix(filename: str) -> str | None:
    lowered: str = filename.lower()
    for suffix in ARCHIVE_SUFFIXES:
        if lowered.endswith(suffix):
            return suffix
    return None


def parse_bool(value: str) -> bool:
    lowered: str = value.strip().lower()
    if lowered in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "f", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(
        f"Invalid boolean value '{value}'. Use true/false."
    )


def stripped_name(filename: str) -> str:
    current: str = filename
    while True:
        match_suffix: str | None = detect_archive_suffix(current)
        if not match_suffix:
            break
        current = current[: len(current) - len(match_suffix)]
        if not current:
            return filename
    return current


def is_archive_name_matched(filename: str, archive_name_regex: re.Pattern[str] | None) -> bool:
    if archive_name_regex is None:
        return True
    normalized_name: str = stripped_name(filename)
    return bool(archive_name_regex.search(normalized_name))


def find_archives(root_dir: Path, archive_name_regex: re.Pattern[str] | None = None) -> list[Path]:
    archives: list[Path] = []
    for dir_path, _, filenames in os.walk(root_dir):
        base_dir: Path = Path(dir_path)
        for filename in filenames:
            if detect_archive_suffix(filename):
                if is_archive_name_matched(filename, archive_name_regex):
                    archives.append(base_dir / filename)
                else:
                    print(f"Skipped '{base_dir / filename}' because it doesn't match --archive_name_regex {archive_name_regex}", file=sys.stderr)
           
    return archives


@dataclass
class ExtractResult:
    archive_path: Path
    extract_dir: Path
    success: bool
    error: str | None = None
    elapsed_seconds: float = 0.0


def extract_stream_archive(archive_path: Path, output_file: Path, suffix: str) -> None:
    if suffix == ".gz":
        with gzip.open(archive_path, "rb") as src, output_file.open("wb") as dst:
            shutil.copyfileobj(src, dst)
    elif suffix == ".bz2":
        with bz2.open(archive_path, "rb") as src, output_file.open("wb") as dst:
            shutil.copyfileobj(src, dst)
    elif suffix == ".xz":
        with lzma.open(archive_path, "rb") as src, output_file.open("wb") as dst:
            shutil.copyfileobj(src, dst)
    elif suffix == ".zst":
        with output_file.open("wb") as dst:
            subprocess.run(["zstd", "-dc", str(archive_path)], check=True, stdout=dst)
    else:
        raise ValueError(f"Unsupported stream archive suffix: {suffix}")


def extract_archive(archive_path: Path, suffix: str, extract_dir: Path) -> None:
    if suffix in TAR_SUFFIXES:
        with tarfile.open(archive_path, "r:*") as tar_fp:
            tar_fp.extractall(path=extract_dir)
        return
    if suffix == ".tar.zst":
        subprocess.run(["tar", "-x", "--zstd", "-f", str(archive_path), "-C", str(extract_dir)], check=True)
        return
    if suffix == ".zip":
        with zipfile.ZipFile(archive_path) as zip_fp:
            zip_fp.extractall(path=extract_dir)
        return
    if suffix in (".gz", ".bz2", ".xz", ".zst"):
        output_name: str = archive_path.name[: len(archive_path.name) - len(suffix)]
        output_file: Path = extract_dir / output_name
        extract_stream_archive(archive_path, output_file, suffix)
        return
    if suffix == ".7z":
        subprocess.run(["7z", "x", "-y", f"-o{extract_dir}", str(archive_path)], check=True)
        return
    if suffix == ".rar":
        subprocess.run(["unrar", "x", "-o+", str(archive_path), f"{extract_dir}/"], check=True)
        return
    raise ValueError(f"Unsupported archive suffix: {suffix}")


def build_output_root(root_dir: Path) -> Path:
    base_name: str = root_dir.name or "root"
    return root_dir.parent / f"UNTAR_{base_name}"


def build_output_root_for_archive(archive_path: Path) -> Path:
    base_name: str = stripped_name(archive_path.name) or archive_path.stem or "root"
    return archive_path.parent / f"UNTAR_{base_name}"


def copy_non_archive_file(src_file: Path, dst_file: Path) -> None:
    dst_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_file, dst_file)
    print(f"Copied file: {src_file} -> {dst_file}", flush=True)


def copy_non_archive_tree(source_root: Path, output_root: Path) -> tuple[int, int]:
    copied_count: int = 0
    skipped_archive_count: int = 0
    print(f"Mirroring non-archive files: {source_root} -> {output_root}", flush=True)
    for dir_path, _, filenames in os.walk(source_root):
        src_dir: Path = Path(dir_path)
        relative_dir: Path = src_dir.relative_to(source_root)
        dst_dir: Path = output_root / relative_dir
        dst_dir.mkdir(parents=True, exist_ok=True)
        for filename in filenames:
            src_file: Path = src_dir / filename
            if detect_archive_suffix(filename):
                skipped_archive_count += 1
                print(f"Skipped archive file copy: {src_file}", flush=True)
                continue
            copy_non_archive_file(src_file, dst_dir / filename)
            copied_count += 1
    print(
        f"Mirror summary: copied {copied_count} non-archive file(s), skipped {skipped_archive_count} archive file(s)",
        flush=True,
    )
    return copied_count, skipped_archive_count


def prepare_output_root(output_root: Path, source_root: Path) -> None:
    source_resolved: Path = source_root.resolve()
    output_resolved: Path = output_root.resolve()
    if output_resolved == source_resolved:
        raise ValueError(f"Refusing to clean output directory because it matches source directory: {output_root}")
    if output_root.exists() and not output_root.is_dir():
        raise ValueError(f"Output path exists and is not a directory: {output_root}")
    if output_root.is_dir():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)


def resolve_extract_dir(archive_path: Path, source_root: Path, output_root: Path) -> Path:
    stripped: str = stripped_name(archive_path.name)
    try:
        relative_parent: Path = archive_path.parent.relative_to(source_root)
        return output_root / relative_parent / stripped
    except ValueError:
        return archive_path.parent / stripped


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def extract_one_archive(archive_path: Path, extract_dir: Path, should_remove_archive: bool) -> ExtractResult:
    suffix: str | None = detect_archive_suffix(archive_path.name)
    if suffix is None:
        return ExtractResult(archive_path=archive_path, extract_dir=archive_path.parent, success=False, error="unsupported suffix")

    started_at: float = time.perf_counter()
    try:
        extract_dir.mkdir(parents=True, exist_ok=True)
        extract_archive(archive_path, suffix, extract_dir)
        if should_remove_archive:
            archive_path.unlink()
        return ExtractResult(archive_path=archive_path, extract_dir=extract_dir, success=True, elapsed_seconds=time.perf_counter() - started_at)
    except Exception as exc:
        return ExtractResult(
            archive_path=archive_path,
            extract_dir=extract_dir,
            success=False,
            error=str(exc),
            elapsed_seconds=time.perf_counter() - started_at,
        )


def extract_nested(
    root_dir: Path,
    output_root: Path,
    should_remove_orig_dir: bool,
    jobs: int,
    archive_name_regex: re.Pattern[str] | None = None,
) -> tuple[int, int]:
    scheduled: set[str] = set()
    processed: set[str] = set()
    extracted_count: int = 0
    failed_count: int = 0

    regex_label: str = archive_name_regex.pattern if archive_name_regex is not None else "<none>"
    print(f"Scanning {root_dir} for archives with {jobs} jobs (archive_name_regex={regex_label})", flush=True)
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures: dict[Future[ExtractResult], tuple[Path, float]] = {}

        def submit_archive(path: Path) -> None:
            key: str = str(path)
            if key in scheduled or key in processed:
                return
            if not path.is_file():
                return
            suffix: str | None = detect_archive_suffix(path.name)
            if suffix is None:
                return
            extract_dir: Path = resolve_extract_dir(path, root_dir, output_root)
            should_remove_archive: bool = should_remove_orig_dir if is_within(path, root_dir) else True
            print(f"Extracting: {path} -> {extract_dir}", flush=True)
            futures[pool.submit(extract_one_archive, path, extract_dir, should_remove_archive)] = (path, time.perf_counter())
            scheduled.add(key)

        for archive_path in find_archives(root_dir, archive_name_regex):
            submit_archive(archive_path)

        while futures:
            done_set, _ = wait(set(futures.keys()), return_when=FIRST_COMPLETED)
            for done_future in done_set:
                archive_path, submitted_at = futures.pop(done_future)
                archive_key: str = str(archive_path)
                processed.add(archive_key)
                try:
                    result: ExtractResult = done_future.result()
                except Exception as exc:
                    failed_count += 1
                    print(f"Completed: {archive_path} [failed] in {time.perf_counter() - submitted_at:.3f}s", flush=True)
                    print(f"  ERROR extracting {archive_path}: {exc}", file=sys.stderr)
                    continue

                status: str = "ok" if result.success else "failed"
                print(f"Completed: {result.archive_path} [{status}] in {result.elapsed_seconds:.3f}s", flush=True)
                if result.success:
                    extracted_count += 1
                else:
                    failed_count += 1
                    print(f"  ERROR extracting {result.archive_path}: {result.error}", file=sys.stderr)

                if result.extract_dir.is_dir():
                    for nested_archive in find_archives(result.extract_dir, archive_name_regex):
                        submit_archive(nested_archive)

    return extracted_count, failed_count


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="deep_extract.py",
        description="Recursively extract all nested archives in a directory or archive.",
    )
    parser.add_argument(
        "--input_dir_or_archive",
        "--input_dir",
        dest="input_dir_or_archive",
        required=True,
        help="Target directory or archive file to scan/extract recursively.",
    )
    parser.add_argument("--should_remove_orig_dir", default=False, type=parse_bool, help="Whether to remove extracted archives from the input tree (true/false). Default: false.")
    parser.add_argument(
        "--archive_name_regex",
        default=None,
        help=(
            "Only extract archives whose stripped filename matches this regex. "
            "Example: '^(350928590056204|350928590056205|master|backup|live)'"
        ),
    )

    default_jobs_count: int = multiprocessing.cpu_count()
    parser.add_argument("-j", "--jobs", type=int, default=default_jobs_count, help=f"Number of concurrent extraction workers. Default: {default_jobs_count}")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    cli_argv: list[str] = sys.argv[1:] if argv is None else argv
    args: argparse.Namespace = parse_args(cli_argv)
    input_path: Path = Path(args.input_dir_or_archive).expanduser()
    used_legacy_flag: bool = any(arg == "--input_dir" or arg.startswith("--input_dir=") for arg in cli_argv)
    if used_legacy_flag:
        print("Warning: --input_dir is deprecated; use --input_dir_or_archive instead.", file=sys.stderr)

    should_remove_orig_dir: bool = bool(args.should_remove_orig_dir)
    jobs: int = int(args.jobs)
    archive_name_regex: re.Pattern[str] | None = None
    if args.archive_name_regex:
        try:
            archive_name_regex = re.compile(args.archive_name_regex)
        except re.error as exc:
            print(f"Error: invalid --archive_name_regex: {exc}", file=sys.stderr)
            return 1
    if jobs < 1:
        print("Error: --jobs must be >= 1.", file=sys.stderr)
        return 1

    with ExitStack() as stack:
        if input_path.is_dir():
            root_dir: Path = input_path
            output_root: Path = build_output_root(input_path)
        elif input_path.is_file():
            suffix: str | None = detect_archive_suffix(input_path.name)
            if suffix is None:
                print(f"Error: '{input_path}' is a file but not a supported archive.", file=sys.stderr)
                return 1
            temp_root: Path = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="deep_extract_")))
            root_dir = temp_root / (stripped_name(input_path.name) or "root")
            root_dir.mkdir(parents=True, exist_ok=True)
            print(f"Pre-extracting input archive: {input_path} -> {root_dir}", flush=True)
            try:
                extract_archive(input_path, suffix, root_dir)
            except Exception as exc:
                print(f"Error: failed to extract input archive '{input_path}': {exc}", file=sys.stderr)
                return 1
            output_root = build_output_root_for_archive(input_path)
        else:
            print(f"Error: '{input_path}' is not a valid directory or archive file.", file=sys.stderr)
            return 1

        try:
            prepare_output_root(output_root, root_dir)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        start_time: float = time.perf_counter()
        copied_count, skipped_archive_count = copy_non_archive_tree(root_dir, output_root)
        extracted_count, failed_count = extract_nested(root_dir, output_root, should_remove_orig_dir, jobs, archive_name_regex)
        print(
            f"Done. Copied {copied_count} plain file(s), skipped {skipped_archive_count} archive file(s) during mirror; "
            f"extracted {extracted_count} archive(s), failed {failed_count}, source={input_path}, output={output_root} "
            f"(scan_root={root_dir}, should_remove_orig_dir={str(should_remove_orig_dir).lower()}, jobs={jobs}, "
            f"archive_name_regex={archive_name_regex.pattern if archive_name_regex is not None else '<none>'})"
        )
        print(f"Total time: {time.perf_counter() - start_time:.3f}s")
        return 0 if failed_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
