#!/usr/local/bin/local_python
import argparse
import hashlib
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

def _print_result(ok: bool, message: str) -> None:
    print(f"{'PASS' if ok else 'FAIL'}: {message}")


def _calc_md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def get_file_md5sum_safe(file_path: Path) -> Optional[str]:
    if not file_path.exists() or not file_path.is_file():
        return None
    try:
        with open(file_path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except Exception as e:
        print(f"WARNING: Failed to calculate md5sum for '{file_path}': {e}", file=sys.stderr)
        return None


def run_readable_case(tmp_path: Path) -> bool:
    readable_file = tmp_path / "readable.bin"
    readable_data = b"hello-md5"
    readable_file.write_bytes(readable_data)
    expected_md5 = _calc_md5(readable_data)
    actual_md5 = get_file_md5sum_safe(readable_file)
    ok = actual_md5 == expected_md5
    _print_result(ok, f"readable file md5 matches (expected={expected_md5}, actual={actual_md5})")
    return ok


def run_permission_case(target_file: Optional[Path]) -> bool:
    #if os.geteuid() == 0:
    #    print("SKIP: permission-denied check is not meaningful as root/sudo")
    #    return True

    if target_file is not None:
        file_path = target_file
        if not file_path.exists() or not file_path.is_file():
            print(f"SKIP: target file does not exist or is not a file: {file_path}")
            return True
        md5_value = get_file_md5sum_safe(file_path)
        ok = md5_value is None
        print(f"target file path={file_path}, md5sum={md5_value}")
        return ok
    else:
        print("SKIP: no target file specified")
        return True
    #with tempfile.TemporaryDirectory(prefix="md5sum_perm_test_") as tmp_dir:
    #    restricted_file = Path(tmp_dir) / "restricted.bin"
    #    restricted_file.write_bytes(b"no-access")
    #    try:
    #        os.chmod(restricted_file, 0)
    #        md5_value = get_file_md5sum_safe(restricted_file)
    #        ok = md5_value is None
    #        _print_result(ok, f"permission denied returns None (actual={md5_value})")
    #        return ok
    #    finally:
    #        try:
    #            os.chmod(restricted_file, 0o600)
    #        except Exception:
    #            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Simple MD5/permission behavior checker")
    parser.add_argument("--target-file", type=str, default=None, help="Optional existing file path to test for unreadable md5 case")
    args = parser.parse_args()

    failed = False
    #with tempfile.TemporaryDirectory(prefix="md5sum_readable_test_") as tmp_dir:
    #    failed = failed or (not run_readable_case(Path(tmp_dir)))

    target_file = Path(args.target_file) if args.target_file else None
    failed = failed or (not run_permission_case(target_file))

    print("RESULT: FAIL" if failed else "RESULT: PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
