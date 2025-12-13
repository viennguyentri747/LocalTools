#!/home/vien/local_tools/MyVenvFolder/bin/python

import sys
import os
import argparse
import subprocess
import shlex
from typing import List, Dict
import tempfile
import shutil
from dev.dev_common.constants import OW_SW_PATH
from dev.dev_common.core_utils import run_shell

CPPCHECK_ENABLE_OPTIONS: Dict[int, str] = {
    1: 'all',
    2: 'warning',
    3: 'style',
    4: 'performance',
    5: 'portability',
    6: 'information',
    7: 'unusedFunction',
    8: 'missingInclude'
}


def build_cppcheck_cmd(inputs: List[str], ignore_dirs: List[str]) -> List[str]:
    print(f"\nAvailable options for cppcheck:")
    for num, opt in CPPCHECK_ENABLE_OPTIONS.items():
        print(f"  {num}. {opt}")
    print("  (Default: error)")

    options_choice = input("Enter option numbers separated by space (e.g., '2 3 7'), or press Enter for none: ").strip()
    chosen_options = []
    if options_choice:
        try:
            chosen_nums = [int(n) for n in options_choice.split()]
            chosen_options = [CPPCHECK_ENABLE_OPTIONS[n] for n in chosen_nums if n in CPPCHECK_ENABLE_OPTIONS]
        except ValueError:
            print("Invalid option numbers. Using default.")

    cmd = ['cppcheck']
    if chosen_options:
        cmd.append(f'--enable={",".join(chosen_options)}')

    # ✅ Use correct -i syntax
    for ignore_dir in ignore_dirs:
        cmd.extend(['-i', ignore_dir])

    cmd.extend(inputs)
    return cmd


def build_clang_tidy_cmd(inputs: List[str], ignore_dirs: List[str]) -> List[str]:
    print("Running clang-tidy syntax checks...")
    tidy_cmd = ['clang-tidy']
    # Note: clang-tidy does not support directories
    for path in inputs:
        if os.path.isdir(path):
            for root, _, files in os.walk(path):
                # Check if the current directory is in the ignore list
                if any(root.startswith(ignore_dir) for ignore_dir in ignore_dirs):
                    print(f"Ignoring directory: {root}")
                    continue
                for f in files:
                    if os.path.splitext(f)[1] in {'.c', '.cpp', '.cc', '.cxx'}:
                        tidy_cmd.append(os.path.join(root, f))
        elif os.path.isfile(path) and os.path.splitext(path)[1] in {'.c', '.cpp', '.cc', '.cxx'}:
            # Check if the file's directory is in the ignore list
            if any(os.path.dirname(path).startswith(ignore_dir) for ignore_dir in ignore_dirs):
                print(f"Ignoring file: {path}")
                continue
            tidy_cmd.append(path)
    tidy_cmd.append('--')
    return tidy_cmd


def generate_compile_commands_from_cmake(cmake_path: str) -> bool:
    cmake_dir = os.path.abspath(os.path.dirname(cmake_path))
    build_dir = tempfile.mkdtemp(prefix="cmake_build_")

    print(f"Generating compile_commands.json from {cmake_path} ...")

    cmake_cmd = [
        "cmake",
        "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
    ]

    extra_cmake_args = []
    cmake_dir_name = os.path.basename(cmake_dir)
    if cmake_dir_name == IESA_ADC_LIB_REPO_NAME or cmake_dir_name == IESA_INTELLIAN_PKG_REPO_NAME:
        extra_cmake_args = [
            f"-DEXTERNAL_DIRS={OW_SW_PATH}/external/",
            f"-DOUTPUT_DIR={OW_SW_PATH}/tmp_build/out/",
        ]
        print(f"Adding extra cmake arguments: {extra_cmake_args}")
    else:
        print(f"Skipping extra cmake arguments for {cmake_dir_name}")

    cmake_cmd.extend(extra_cmake_args)
    cmake_cmd.append(cmake_dir)

    result = subprocess.run(cmake_cmd, cwd=build_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(result.stdout.decode())

    compile_commands = os.path.join(build_dir, "compile_commands.json")
    if os.path.exists(compile_commands):
        shutil.copy(compile_commands, "./compile_commands.json")
        print("✅ compile_commands.json generated and copied.")
        return True
    else:
        print("❌ Failed to generate compile_commands.json")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="C/C++ Static Checker Wrapper")
    parser.add_argument('-i', '--inputs', nargs='+', required=True, help="Files or directories to analyze")
    parser.add_argument('--ignore-dirs', nargs='*', default=[], help="Directories to ignore during analysis")
    parser.add_argument('--cmake', required=False, help="Path to CMakeLists.txt (for generating compile_commands.json)")
    args = parser.parse_args()

    input_files_or_dirs: List[str] = args.inputs
    ignore_dirs: List[str] = args.ignore_dirs

    # Generate compile_commands.json if needed
    skip_tidy = False
    if args.cmake:
        success = generate_compile_commands_from_cmake(args.cmake)
        if not success:
            skip_tidy = True
    else:
        print("No CMakeLists.txt input provided. Skipping clang-tidy.")
        skip_tidy = True

    if not skip_tidy:
        clang_tidy_cmd = build_clang_tidy_cmd(input_files_or_dirs, ignore_dirs)
        run_shell(clang_tidy_cmd, check_throw_exception_on_exit_code=False)

    cppcheck_cmd = build_cppcheck_cmd(input_files_or_dirs, ignore_dirs)
    run_shell(cppcheck_cmd, check_throw_exception_on_exit_code=False)


if __name__ == '__main__':
    main()
