#!/usr/bin/env python3
import shutil
from pathlib import Path
import subprocess
import re
from utils import run_shell
import pyperclip


def main():
    # Step 1: Copy .gitlab-ci.yml to .tmp-local-gitlab-ci.yml
    orig_gl_yml_file = Path(".gitlab-ci.yml")
    tmp_gl_yml_file = Path(".tmp-local-gitlab-ci.yml")
    if not orig_gl_yml_file.exists():
        raise FileNotFoundError(".gitlab-ci.yml not found in current directory")
    shutil.copyfile(orig_gl_yml_file, tmp_gl_yml_file)

    # Step 2: Get all relevant global git config URL rewrites
    result = run_shell(
        "git config --global --get-regexp '^url\\..*\\.insteadOf$'",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    # Build a mapping of insteadOf -> full URL (with token)
    replacements = {}
    print(f"Found: {result.stdout}")
    for line in result.stdout.strip().splitlines():
        # url.https://gitlab-ci-token:gl.....@gitlab.com/intellian_adc/.insteadof https://gitlab.com/intellian_adc/
        match = re.match(r'^url\.(.+?)\.insteadof\s+(.+)$', line, re.IGNORECASE)
        if match:
            full_url, original_url = match.groups()
            replacements[original_url] = full_url
            print(f"Found Original URL: \"{original_url}\", Replacing with \"{full_url}\"")

    # Step 3: Replace matching lines in the copied file
    content = tmp_gl_yml_file.read_text()
    for original_url, full_url in replacements.items():
        # This replaces ONLY the actual URL part — not the full git command
        escaped_original_url = re.escape(original_url)
        replacement_url = full_url

        # Optional: match and replace only inside git config lines
        pattern = rf"(git\s+config\s+--global\s+url\.).+?(\.insteadof\s+{escaped_original_url})"
        replacement = rf"\1{replacement_url}\2"
        
        print(f"[DEBUG] Regex pattern: {pattern}, replacement: {replacement}")
        print(f"[DEBUG] Replacing: {original_url} → {replacement_url}")
        content, count = re.subn(pattern, replacement, content, flags=re.IGNORECASE)
        print(f"[DEBUG] Replaced {count} occurrence(s)")

    # Write modified content back
    tmp_gl_yml_file.write_text(content)

    # Step 4: Print the resulting file
    #print(content)

    ## Step 5: print gitlab-ci-local with generated .tmp-local-gitlab-ci.yml
    #print(f"gitlab-ci-local --file {tmp_gl_yml_file.name}")
    command = f"gitlab-ci-local --file {tmp_gl_yml_file.name}"
    pyperclip.copy(command)
    print(f"{command}  [✔ copied to clipboard]")

if __name__ == "__main__":
    main()