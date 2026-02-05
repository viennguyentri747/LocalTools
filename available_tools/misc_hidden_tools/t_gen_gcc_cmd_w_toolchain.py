#!/home/vien/core_repos/local_tools/MyVenvFolder/bin/python
"""
Generate gcc/g++ commands from a CMake toolchain file.

This script parses the provided toolchain file, extracts the compiler,
sysroot, and relevant flags, then prints a ready-to-use compilation
command using placeholder source/output names that can be tweaked
quickly from the clipboard.
"""

from __future__ import annotations

import argparse
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List

from dev.dev_common import *
MODE_C = "c"
MODE_CPP = "cpp"
MODE_CHOICES = (MODE_C, MODE_CPP)

DEFAULT_STD_FLAG = {
    MODE_C: "-std=c11",
    MODE_CPP: "-std=c++17",
}

PLACEHOLDER_SOURCES = {
    MODE_C: ["file1.c", "file2.c"],
    MODE_CPP: ["file1.cpp", "file2.cpp"],
}

PLACEHOLDER_OUTPUT = "test_program"
DEFAULT_DEFINES = ("-D_IESA_SUPPORT_",)
DEFAULT_INCLUDE = "-I."
DEFAULT_LIBS = ("-lpthread",)

SET_PATTERN = re.compile(r"set\s*\(\s*([A-Za-z0-9_]+)\s+(.+?)\)", re.IGNORECASE | re.DOTALL)
ARG_TOOL_CHAIN_PATH = f"{ARGUMENT_LONG_PREFIX}toolchain_path"


@dataclass
class ToolchainSettings:
    c_compiler: str | None = None
    cxx_compiler: str | None = None
    sysroot: str | None = None
    find_root_paths: List[str] = field(default_factory=list)
    c_flags: List[str] = field(default_factory=list)
    cxx_flags: List[str] = field(default_factory=list)
    linker_flags: List[str] = field(default_factory=list)


def get_tool_templates() -> List[ToolTemplate]:
    ARM_TOOLCHAIN_PATH = f"{OW_SW_BUILD_TOOLS_PATH}/ToolChain_adc_apps.cmake"
    return [
        ToolTemplate(
            name="Generate g++ command from ARM ToolChain",
            extra_description="Use the cross C++ compiler defined inside the toolchain file.",
            args={
                ARG_MODE: MODE_CPP,
                ARG_TOOL_CHAIN_PATH: f"{ARM_TOOLCHAIN_PATH}"
            },
            should_run_now=True,
        ),
        ToolTemplate(
            name="Generate gcc command from ARM ToolChain",
            extra_description="Same as above but target the C compiler.",
            args={
                ARG_MODE: MODE_C,
                ARG_TOOL_CHAIN_PATH: f"{ARM_TOOLCHAIN_PATH}"
            },
            should_run_now=True,
        ),
    ]


def parse_toolchain_file(toolchain_path: Path) -> ToolchainSettings:
    if not toolchain_path.is_file():
        raise FileNotFoundError(f"Toolchain file not found: {toolchain_path}")

    content = toolchain_path.read_text()
    raw_settings: dict[str, str] = {}

    for match in SET_PATTERN.finditer(content):
        key = match.group(1).strip().upper()
        value = match.group(2).strip()
        if "#" in value:
            value = value.split("#", 1)[0].strip()
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        raw_settings[key] = value

    def split_flags(value: str | None) -> List[str]:
        return shlex.split(value) if value else []

    def split_paths(value: str | None) -> List[str]:
        if not value:
            return []
        return [part.strip() for part in value.split(";") if part.strip()]

    return ToolchainSettings(
        c_compiler=raw_settings.get("CMAKE_C_COMPILER"),
        cxx_compiler=raw_settings.get("CMAKE_CXX_COMPILER"),
        sysroot=raw_settings.get("CMAKE_SYSROOT"),
        find_root_paths=split_paths(raw_settings.get("CMAKE_FIND_ROOT_PATH")),
        c_flags=split_flags(raw_settings.get("CMAKE_C_FLAGS")),
        cxx_flags=split_flags(raw_settings.get("CMAKE_CXX_FLAGS")),
        linker_flags=split_flags(raw_settings.get("CMAKE_EXE_LINKER_FLAGS")),
    )


def build_root_search_flags(root_paths: Iterable[str]) -> List[str]:
    include_suffixes = ("include", "usr/include")
    lib_suffixes = ("lib", "usr/lib")
    flags: List[str] = []

    def append_unique(values: Iterable[str]) -> None:
        seen = {flag for flag in flags}
        for value in values:
            if value not in seen:
                flags.append(value)
                seen.add(value)

    for root in root_paths:
        root_path = Path(root)
        include_flags = [f"-I{root_path / suffix}" for suffix in include_suffixes]
        lib_flags = [f"-L{root_path / suffix}" for suffix in lib_suffixes]
        append_unique(include_flags + lib_flags)

    return flags


def build_compilation_command(settings: ToolchainSettings, mode: str) -> str:
    compiler = settings.cxx_compiler if mode == MODE_CPP else settings.c_compiler
    if not compiler:
        raise ValueError(f"No compiler found for mode '{mode}'. Check the toolchain file.")

    command_parts: List[str] = [compiler]

    if settings.sysroot:
        command_parts.append(f"--sysroot={settings.sysroot}")

    lang_flags = settings.cxx_flags if mode == MODE_CPP else settings.c_flags
    command_parts.extend(lang_flags)
    command_parts.extend(build_root_search_flags(settings.find_root_paths))
    command_parts.append(DEFAULT_INCLUDE)
    command_parts.extend(DEFAULT_DEFINES)
    command_parts.append(DEFAULT_STD_FLAG[mode])
    command_parts.extend(PLACEHOLDER_SOURCES[mode])
    command_parts.extend(settings.linker_flags)
    command_parts.extend(DEFAULT_LIBS)
    command_parts.extend(["-o", PLACEHOLDER_OUTPUT])
    return " ".join(shlex.quote(part) for part in command_parts if part)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate gcc/g++ commands from a CMake toolchain file.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(get_tool_templates(), Path(__file__))
    parser.add_argument(
        ARG_TOOL_CHAIN_PATH,
        required=True,
        help="Path to the CMake toolchain file (e.g. ToolChain_arm32.9.2.cmake).",
    )
    parser.add_argument(
        ARG_MODE,
        choices=MODE_CHOICES,
        default=MODE_CPP,
        help=f"Compilation mode ({MODE_C} or {MODE_CPP}). Defaults to {MODE_CPP}.",
    )
    args = parser.parse_args()

    toolchain_path = Path(get_arg_value(args, ARG_TOOL_CHAIN_PATH)).expanduser()
    mode = get_arg_value(args, ARG_MODE)

    settings = parse_toolchain_file(toolchain_path)
    command = build_compilation_command(settings, mode)

    LOG("Detected toolchain settings:")
    LOG(f"  C compiler : {settings.c_compiler or 'N/A'}")
    LOG(f"  C++ compiler: {settings.cxx_compiler or 'N/A'}")
    LOG(f"  Sysroot     : {settings.sysroot or 'N/A'}")
    if settings.find_root_paths:
        LOG("  Root paths  :")
        for root in settings.find_root_paths:
            LOG(f"    - {root}")
    else:
        LOG("  Root paths  : N/A")

    LOG("\nGenerated command:\n")
    LOG(command)
    display_content_to_copy(command, purpose="compile sources")


if __name__ == "__main__":
    main()
