#!/home/vien/local_tools/MyVenvFolder/bin/python
import os
import shutil
from pathlib import Path
import subprocess
import re
import sys
import argparse
from pathlib import Path
from dev_common import *
from dev_common.tools_utils import ToolTemplate
import pyperclip


def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="Process GitLab CI",
            extra_description="Process .gitlab-ci.yml for local execution",
            args={
                "--gl_yml_file_path": "~/core_repos/intellian_pkg/.gitlab-ci.yml",
            }
        ),
    ]


def main():
    parser = argparse.ArgumentParser(description="Process .gitlab-ci.yml for local execution.")
    parser.formatter_class = argparse.RawTextHelpFormatter
    parser.epilog = build_examples_epilog(get_tool_templates(), Path(__file__))

    parser.add_argument(ARG_PATH_SHORT, "--gl_yml_file_path", help="Path to the source .gitlab-ci.yml file")
    args = parser.parse_args()

    orig_gl_yml_file = Path(args.gl_yml_file_path).resolve()
    yml_file_name = ".gitlab-ci.yml"
    if not orig_gl_yml_file.exists() or not orig_gl_yml_file.is_file() or not (orig_gl_yml_file.name == yml_file_name):
        LOG(f"ERROR: Invalid .gitlab-ci.yml file path: {orig_gl_yml_file}", file=sys.stderr)
        exit(1)

    source_folder = orig_gl_yml_file.parent
    tmp_working_folder = source_folder/"tmp_local_gitlab_ci/"
    # Create fresh temp working folder
    if tmp_working_folder.exists():
        shutil.rmtree(tmp_working_folder)
    tmp_working_folder.mkdir(parents=True, exist_ok=True)

    # Step 1: Copy everything from the source directory to the temporary folder using rsync
    LOG(f"Copying contents from {source_folder} to {tmp_working_folder} using rsync...")

    rsync_command = ["rsync", "-a", "--delete"]
    # Exclude some folders from copying (with --delete then those will not exist at all in target folder)
    ignore_folders_from_source = [".vscode", ".git", tmp_working_folder.name]
    for folder in ignore_folders_from_source:
        rsync_command.extend(["--exclude", folder])
    # Specify source and destination
    rsync_command.extend([
        str(source_folder.resolve()) + "/",     # Source path with trailing slash to copy contents
        str(tmp_working_folder)    # Destination path
    ])

    change_dir(source_folder)
    run_shell(rsync_command)
    LOG("Copy complete.")

    change_dir(tmp_working_folder)
    assert tmp_working_folder.exists(), "Temp working folder was not created!"
    tmp_gl_yml_file = tmp_working_folder / yml_file_name
    assert tmp_gl_yml_file.exists(), f"Copied .gitlab-ci.yml not found in temp folder: {tmp_gl_yml_file}"

    # Step 2: Get all relevant global git config URL rewrites
    result_git_url_overwrites = run_shell(
        "git config --global --get-regexp '^url\\..*\\.insteadOf$'",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    # Build a mapping of insteadOf -> full URL (with token)
    replacements = {}
    LOG(f"Found: {result_git_url_overwrites.stdout}")
    for line in result_git_url_overwrites.stdout.strip().splitlines():
        # url.https://gitlab-ci-token:gl.....@gitlab.com/intellian_adc/.insteadOf https://gitlab.com/intellian_adc/
        match = re.match(r'^url\.(.+?)\.insteadof\s+(.+)$', line, re.IGNORECASE)
        if match:
            full_url, original_url = match.groups()
            replacements[original_url] = full_url
            LOG(f"Found Original URL: \"{original_url}\", Replacing with \"{full_url}\"")

    # Step 3: Replace matching lines in the copied file
    content = tmp_gl_yml_file.read_text()
    for original_url, full_url in replacements.items():
        # This replaces ONLY the actual URL part — not the full git command
        escaped_original_url = re.escape(original_url)
        replacement_url = full_url

        # Optional: match and replace only inside git config lines
        pattern = rf"(git\s+config\s+--global\s+url\.).+?(\.insteadof\s+{escaped_original_url})"
        replacement = rf"\1{replacement_url}\2"

        LOG(f"[DEBUG] Regex pattern: {pattern}, replacement: {replacement}")
        LOG(f"[DEBUG] Replacing: {original_url} → {replacement_url}")
        content, count = re.subn(pattern, replacement, content, flags=re.IGNORECASE)
        LOG(f"[DEBUG] Replaced {count} occurrence(s)")

    # Write modified content back
    tmp_gl_yml_file.write_text(content)

    # Step 4: LOG the resulting file
    # LOG(content)

    # --cwd {tmp_working_folder}
    ci_local_command = f"cd {tmp_working_folder} && gitlab-ci-local --file {tmp_gl_yml_file.name}"
    pyperclip.copy(ci_local_command)
    LOG(LINE_SEPARATOR, highlight=True)
    LOG(f"TO BUILD: {ci_local_command}  [✔ copied to clipboard]", highlight=True)
    LOG(LINE_SEPARATOR, highlight=True)

    # List available jobs
    run_shell(f"{ci_local_command} --list")
    LOG(f"Add `--job <job1> <job2>` to run jobs manually", highlight=True)


if __name__ == "__main__":
    main()
