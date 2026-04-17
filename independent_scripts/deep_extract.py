#!/usr/bin/env python3
"""Fast recursive archive extraction utility."""

from __future__ import annotations

import argparse
import bz2
from dataclasses import dataclass
import gzip
import lzma
import multiprocessing
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
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


def find_archives(root_dir: Path) -> list[Path]:
    archives: list[Path] = []
    for dir_path, _, filenames in os.walk(root_dir):
        base_dir: Path = Path(dir_path)
        for filename in filenames:
            if detect_archive_suffix(filename):
                archives.append(base_dir / filename)
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
        pass
    try:
        archive_path.parent.relative_to(output_root)
        return archive_path.parent / stripped
    except ValueError:
        return archive_path.parent / stripped


def extract_one_archive(archive_path: Path, extract_dir: Path, should_remove_orig_tar: bool) -> ExtractResult:
    suffix: str | None = detect_archive_suffix(archive_path.name)
    if suffix is None:
        return ExtractResult(archive_path=archive_path, extract_dir=archive_path.parent, success=False, error="unsupported suffix")

    started_at: float = time.perf_counter()
    try:
        extract_dir.mkdir(parents=True, exist_ok=True)
        extract_archive(archive_path, suffix, extract_dir)
        if should_remove_orig_tar:
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


def extract_nested(root_dir: Path, output_root: Path, should_remove_orig_tar: bool, jobs: int) -> tuple[int, int]:
    scheduled: set[str] = set()
    processed: set[str] = set()
    extracted_count: int = 0
    failed_count: int = 0

    print(f"Scanning {root_dir} for archives with {jobs} jobs", flush=True)
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
            print(f"Extracting: {path} -> {extract_dir}", flush=True)
            futures[pool.submit(extract_one_archive, path, extract_dir, should_remove_orig_tar)] = (path, time.perf_counter())
            scheduled.add(key)

        for archive_path in find_archives(root_dir):
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
                    for nested_archive in find_archives(result.extract_dir):
                        submit_archive(nested_archive)

    return extracted_count, failed_count


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="deep_extract.py",
        description="Recursively extract all nested archives in a directory.",
    )
    parser.add_argument("directory", help="Target directory to scan and extract archives")
    parser.add_argument( "should_remove_orig_tar", nargs="?", default=False, type=parse_bool, help="Optional boolean (true/false). Default: false", )

    default_jobs_count: int = multiprocessing.cpu_count()
    parser.add_argument( "-j", "--jobs", type=int, default=default_jobs_count, help="Number of concurrent extraction workers. Default: 10", )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    cli_argv: list[str] = sys.argv[1:] if argv is None else argv
    args: argparse.Namespace = parse_args(cli_argv)
    root_dir: Path = Path(args.directory).expanduser()

    if not root_dir.is_dir():
        print(f"Error: '{root_dir}' is not a valid directory.", file=sys.stderr)
        return 1

    should_remove_orig_tar: bool = bool(args.should_remove_orig_tar)
    jobs: int = int(args.jobs)
    if jobs < 1:
        print("Error: --jobs must be >= 1.", file=sys.stderr)
        return 1

    output_root: Path = build_output_root(root_dir)
    try:
        prepare_output_root(output_root, root_dir)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    extracted_count, failed_count = extract_nested(root_dir, output_root, should_remove_orig_tar, jobs)
    print(
        f"Done. Extracted {extracted_count} archive(s), failed {failed_count}, source={root_dir}, output={output_root} "
        f"(should_remove_orig_tar={str(should_remove_orig_tar).lower()}, jobs={jobs})"
    )
    return 0 if failed_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
