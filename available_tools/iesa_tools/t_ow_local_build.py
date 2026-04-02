#!/usr/local/bin/local_python
"""
OneWeb SW-Tools interactive local build helper (top-down, manifest-aware).
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import textwrap
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from dev.dev_common import *
from dev.dev_common.gitlab_utils import *
from dev.dev_iesa import *
import yaml
import traceback

GITLAB_CI_YML_PATH = OW_SW_PATH / ".gitlab-ci.yml"
# Need to put this here because we will go into docker environment from OW_SW_PATH
BSP_ARTIFACT_FOLDER_PATH = OW_SW_PATH / "custom_artifacts_bsp/"
BSP_ARTIFACT_PREFIX = "bsp-iesa-"
BSP_SYMLINK_PATH_FOR_BUILD = OW_SW_PATH / "packaging" / "bsp_current" / "bsp_current.tar.xz"
MAIN_STEP_LOG_PREFIX = f"{LINE_SEPARATOR}\n[MAIN_STEP]"
# ARGs
ARG_MANIFEST_SOURCE = f"{ARGUMENT_LONG_PREFIX}manifest_source"
ARG_TISDK_REF = f"{ARGUMENT_LONG_PREFIX}tisdk_ref"
ARG_OVERWRITE_REPOS = f"{ARGUMENT_LONG_PREFIX}overwrite_repos"
ARG_INTERACTIVE_SHORT = f"{ARGUMENT_SHORT_PREFIX}i"
ARG_MAKE_CLEAN = f"{ARGUMENT_LONG_PREFIX}make_clean"
ARG_IS_DEBUG_BUILD = f"{ARGUMENT_LONG_PREFIX}is_debug_build"
ARG_OW_BUILD_TYPE = f"{ARGUMENT_LONG_PREFIX}build_type"
ARG_RUN_VIA_PYTHON = f"{ARGUMENT_LONG_PREFIX}run_via_python"
PREFIX_OW_BUILD_ARTIFACT = f"iesa_test_"
WIN_CMD_INVOCATION = get_win_cmd_invocation("available_tools.iesa_tools.t_ow_local_build")
IESA_TEST_DIFF_PREFIX = f"iesa_test_diff_"
IESA_METADATA_FILE = f"iesa_ow_build_metadata.json"
TEMP_OW_BUILD_OUTPUT_PATH = PERSISTENT_TEMP_PATH / "ow_build_output/"
MANIFEST_OUT_ARTIFACT_PATH = TEMP_OW_BUILD_OUTPUT_PATH / f"{PREFIX_OW_BUILD_ARTIFACT}manifest.xml"
IESA_OUT_ARTIFACT_PATH = TEMP_OW_BUILD_OUTPUT_PATH / f"{PREFIX_OW_BUILD_ARTIFACT}build.iesa"
LOG_OUT_PATH = TEMP_OW_BUILD_OUTPUT_PATH / f"{PREFIX_OW_BUILD_ARTIFACT}log.txt"
COPY_TO_UT_RUNNER_PATH = Path(__file__).resolve().parent / "copy_to_ut_runner.py"
LOCAL_PYTHON_BIN = "/usr/local/bin/local_python"

def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="Build IESA (.iesa) using current branch in local manifest",
            extra_description=f"{NOTE_AVAILABLE_LOCAL_COMPONENT_REPO_NAMES}",
            args={
                ARG_INTERACTIVE: False,
                ARG_OW_BUILD_TYPE: BUILD_TYPE_IESA,
                ARG_RUN_VIA_PYTHON: True,
                ARG_MANIFEST_SOURCE: MANIFEST_SOURCE_LOCAL,
                ARG_BASE_MANIFEST_BRANCH: BRANCH_AERO_MASTER,
                ARG_TISDK_REF: BRANCH_AERO_MASTER,
                ARG_MAKE_CLEAN: True,
                ARG_IS_DEBUG_BUILD: True,
                ARG_OVERWRITE_REPOS: [IESA_INTELLIAN_PKG_REPO_NAME, IESA_INSENSE_SDK_REPO_NAME],
            },
            # override_cmd_invocation=WIN_CMD_INVOCATION,
        ),
        ToolTemplate(
            name="Build BINARY using current branch in local manifest",
            extra_description=f"{NOTE_AVAILABLE_LOCAL_COMPONENT_REPO_NAMES}",
            args={
                ARG_INTERACTIVE: False,
                ARG_OW_BUILD_TYPE: BUILD_TYPE_BINARY,
                ARG_RUN_VIA_PYTHON: True,
                ARG_MANIFEST_SOURCE: MANIFEST_SOURCE_LOCAL,
                ARG_BASE_MANIFEST_BRANCH: BRANCH_AERO_MASTER,
                ARG_MAKE_CLEAN: True,
                ARG_IS_DEBUG_BUILD: True,
                ARG_OVERWRITE_REPOS: [IESA_INTELLIAN_PKG_REPO_NAME, IESA_INSENSE_SDK_REPO_NAME],
            },
            # override_cmd_invocation=WIN_CMD_INVOCATION,
        ),
        ToolTemplate(
            name="Build IESA using current branch in remote manifest",
            extra_description=f"{NOTE_AVAILABLE_LOCAL_COMPONENT_REPO_NAMES}",
            args={
                ARG_INTERACTIVE: False,
                ARG_OW_BUILD_TYPE: BUILD_TYPE_IESA,
                ARG_MANIFEST_SOURCE: MANIFEST_SOURCE_REMOTE,
                ARG_BASE_MANIFEST_BRANCH: BRANCH_MANPACK_MASTER,
                ARG_TISDK_REF: BRANCH_MANPACK_MASTER,
                ARG_MAKE_CLEAN: True,
                ARG_IS_DEBUG_BUILD: True,
                ARG_OVERWRITE_REPOS: [IESA_INTELLIAN_PKG_REPO_NAME, IESA_INSENSE_SDK_REPO_NAME],
            },
            hidden=True,
            # override_cmd_invocation=WIN_CMD_INVOCATION,
        ),
    ]



def getToolData() -> ToolData:
    return ToolData(tool_template=get_tool_templates())

def main() -> None:
    parser = argparse.ArgumentParser(description="OneWeb SW-Tools local build helper.")
    parser.formatter_class = argparse.RawTextHelpFormatter
    # Fill help epilog from templates
    parser.epilog = build_examples_epilog(getToolData().tool_template, Path(__file__))
    parser.add_argument(ARG_OW_BUILD_TYPE, choices=[BUILD_TYPE_BINARY, BUILD_TYPE_IESA], type=str, default=BUILD_TYPE_BINARY,
                        help="Build type (binary or iesa). Defaults to binary.")
    parser.add_argument(ARG_MANIFEST_SOURCE, choices=[MANIFEST_SOURCE_LOCAL, MANIFEST_SOURCE_REMOTE], default=MANIFEST_SOURCE_LOCAL,
                        help=F"Source for the manifest repository URL ({MANIFEST_SOURCE_LOCAL} or {MANIFEST_SOURCE_REMOTE}). Defaults to {MANIFEST_SOURCE_LOCAL}. Note that although it is local manifest, the source of sync is still remote so will need to push branch of dependent local repos specified in local manifest (not ow_sw_tools).")
    parser.add_argument(ARG_BASE_MANIFEST_BRANCH, default=BRANCH_MANPACK_MASTER,
                        help=f"Base branch to validate current OW branch against on remote '{DEFAULT_OW_GIT_REMOTE}'. Current OW branch must be ahead/descendant of this base branch. Ex: {BRANCH_MANPACK_MASTER}")
    parser.add_argument(ARG_TISDK_REF, type=str, default=EMPTY_STR_VALUE,
                        help=f"TISDK Ref for BSP (for creating .iesa). Ex: {BRANCH_MANPACK_MASTER}")
    parser.add_argument(ARG_OVERWRITE_REPOS, nargs='*', default=[],
                        help="List of repository names to overwrite from local")
    parser.add_argument(ARG_INTERACTIVE_SHORT, ARG_INTERACTIVE, type=lambda x: x.lower() == TRUE_STR_VALUE, default=False,
                        help="Run in interactive mode (true or false). Defaults to false.")
    parser.add_argument(ARG_MAKE_CLEAN, type=lambda x: x.lower() == TRUE_STR_VALUE, default=True,
                        help="Run make clean before building (true or false). Defaults to true.")
    parser.add_argument(ARG_IS_DEBUG_BUILD, type=lambda x: x.lower() == TRUE_STR_VALUE, default=False,
                        help="Enable debug build (true or false). Defaults to false.")
    parser.add_argument(ARG_RUN_VIA_PYTHON, type=lambda x: x.lower() == TRUE_STR_VALUE, default=False,
                        help="Display Python-based UT copy runner command instead of the legacy shell copy command (true or false). Defaults to false.")
    args = parser.parse_args()
    LOG(
        textwrap.dedent(
            """\
            -------------------------------
            OneWeb local build orchestrator
            -------------------------------"""
        )
    )
    build_type: str = get_arg_value(args, ARG_OW_BUILD_TYPE)
    # is_overwrite_local_repos: bool = args.is_overwrite_local_repos
    manifest_source: str = get_arg_value(args, ARG_MANIFEST_SOURCE)
    tisdk_ref: Optional[str] = get_arg_value(args, ARG_TISDK_REF)
    overwrite_repos: List[str] = get_arg_value(args, ARG_OVERWRITE_REPOS)
    base_manifest_branch: str = get_arg_value(args, ARG_BASE_MANIFEST_BRANCH)
    make_clean: bool = get_arg_value(args, ARG_MAKE_CLEAN)
    is_debug_build: bool = get_arg_value(args, ARG_IS_DEBUG_BUILD)
    run_via_python: bool = get_arg_value(args, ARG_RUN_VIA_PYTHON)
    # Update overwrite repos no git suffix
    overwrite_repos = [get_path_no_suffix(r, GIT_SUFFIX) for r in overwrite_repos]
    init_ow_build_log()

    append_build_log(f"Build type: {build_type}")
    append_build_log(f"Manifest source: {manifest_source}")
    tisdk_ref_from_ci_yml: Optional[str] = None
    if build_type == BUILD_TYPE_IESA:
        tisdk_ref_from_ci_yml = get_tisdk_ref_from_ci_yml(GITLAB_CI_YML_PATH)
        if not tisdk_ref_from_ci_yml:
            LOG(f"ERROR: Could not determine TISDK ref from '{GITLAB_CI_YML_PATH}'.", file=sys.stderr)
            sys.exit(1)
        if not tisdk_ref:
            tisdk_ref = tisdk_ref_from_ci_yml
            tisdk_arg_dest = ARG_TISDK_REF.lstrip(ARGUMENT_LONG_PREFIX).replace("-", "_")
            setattr(args, tisdk_arg_dest, tisdk_ref)
            LOG(f"No explicit TISDK ref provided. Using '{tisdk_ref}' from '{GITLAB_CI_YML_PATH}'.")

    LOG(f"Parsed args: {args}")
    append_build_log(f"Parsed args: {args}")

    current_branch = git_get_current_branch(OW_SW_PATH)
    if not current_branch:
        LOG(f"ERROR: Unable to determine current branch in '{OW_SW_PATH}'.", file=sys.stderr)
        sys.exit(1)
    ow_manifest_branch = current_branch

    LOG(f"Using current OW branch '{ow_manifest_branch}' as manifest branch.")
    append_build_log(f"Manifest branch: {ow_manifest_branch}")
    append_build_log(f"Base manifest branch: {base_manifest_branch}")
    if tisdk_ref:
        append_build_log(f"TISDK ref: {tisdk_ref}")
    actual_manifest, repo_change_details = setup_prebuild(
        build_type, manifest_source, ow_manifest_branch, base_manifest_branch, tisdk_ref, overwrite_repos,
        current_branch, tisdk_ref_from_ci_yml)

    run_build(build_type, get_arg_value(args, ARG_INTERACTIVE), make_clean, is_debug_build)
    # Always display binary build finish + command to copy
    LOG(f"{MAIN_STEP_LOG_PREFIX} Binary build finished.")
    LOG(f"Find output binary files in '{OW_SW_BUILD_BINARY_OUTPUT_PATH}'")
    LOG(f"{LINE_SEPARATOR}")
    append_build_log("Binary build finished.")
    append_build_log(f"Binary output directory: {OW_SW_BUILD_BINARY_OUTPUT_PATH}")
    command_to_display = (
        f'sudo chmod -R 755 {OW_SW_BUILD_BINARY_OUTPUT_PATH} && '
        f'while true; do '
        f'read -e -p "Enter binary path: " -i "{OW_SW_BUILD_BINARY_OUTPUT_PATH}/" BIN_PATH && '
        f'if [ -f "$BIN_PATH" ]; then break; else echo "Error: File $BIN_PATH does not exist. Please try again."; fi; '
        f'done && '
        f'BIN_NAME=$(basename "$BIN_PATH") && '
        f'DEST_NAME="$BIN_NAME" && '
        f'original_md5=$(md5sum "$BIN_PATH" | cut -d" " -f1) && '
        f'read -e -p "Enter target IP: " -i "192.168.100." TARGET_IP && '
        f'ping_acu_ip "$TARGET_IP" --mute && '
        f'scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -rJ root@$TARGET_IP "$BIN_PATH" root@192.168.100.254:/home/root/download/"$DEST_NAME" && '
        f'{{ '
        f'echo "SCP copy completed successfully"; '
        f'echo -e "Binary copied completed. Setup symlink on target UT $TARGET_IP with this below command:\\n"; '
        f'echo "actual_md5=\\$(md5sum /home/root/download/$DEST_NAME | cut -d\\" \\" -f1) && if [ \\"$original_md5\\" = \\"\\$actual_md5\\" ]; then echo \\"MD5 match! Proceeding...\\" && cp /opt/bin/$BIN_NAME /home/root/download/backup_$BIN_NAME; ln -sf /home/root/download/$DEST_NAME /opt/bin/$BIN_NAME && echo \\"Backup created and symlink updated: /opt/bin/$BIN_NAME -> /home/root/download/$DEST_NAME\\"; else echo \\"MD5 MISMATCH! Aborting.\\"; fi"; '
        f'}} || {{ '
        f'echo "SCP copy failed"; '
        f'}}'
    )
    if run_via_python:
        command_to_display = (
            f'sudo chmod -R 755 {OW_SW_BUILD_BINARY_OUTPUT_PATH} && {shlex.quote(str(COPY_TO_UT_RUNNER_PATH))} '
            f'--mode binary --local_path {shlex.quote(str(OW_SW_BUILD_BINARY_OUTPUT_PATH))}'
        )

    #command_to_display = wrap_cmd_for_bash(command_to_display)
    display_content_to_copy(command_to_display, purpose="Copy BINARY to target IP",
                            is_copy_to_clipboard=(build_type == BUILD_TYPE_BINARY))
    append_build_log("Copy BINARY command:")
    append_build_log(command_to_display)

    # TODO: improve handling on interactive mode (check it actually success before print copy commands)
    iesa_artifact_path: Optional[Path] = None
    # iesa_original_md5: Optional[str] = None
    if build_type == BUILD_TYPE_IESA:
        LOG(f"{MAIN_STEP_LOG_PREFIX} IESA build finished. Renaming artifact...")
        if OW_SW_OUTPUT_IESA_PATH.is_file():
            # safe_branch = sanitize_str_to_file_name(manifest_branch)
            # new_iesa_name = f"{PREFIX_OW_BUILD_ARTIFACT}build.iesa"
            new_iesa_path = IESA_OUT_ARTIFACT_PATH
            ensure_temp_build_output_dir()
            if new_iesa_path.exists():
                new_iesa_path.unlink()

            shutil.move(str(OW_SW_OUTPUT_IESA_PATH), str(new_iesa_path))
            new_iesa_output_abs_path = new_iesa_path.resolve()
            LOG(f"Renamed '{OW_SW_OUTPUT_IESA_PATH.name}' to '{new_iesa_path.name}'")
            LOG(f"Find output IESA here (WSL path): {new_iesa_output_abs_path}")
            append_build_log(f"IESA output path: {new_iesa_output_abs_path}")
            iesa_artifact_path = new_iesa_output_abs_path
            # run_shell(f"sudo chmod 644 {new_iesa_output_abs_path}")
            # iesa_original_md5 = original_md5

            command_to_display = create_scp_ut_and_run_cmd(
                local_path=new_iesa_output_abs_path,
                remote_host="root@192.168.100.254",
                remote_dir="/home/root/download/",
                run_cmd_on_remote=create_install_iesa_cmd(new_iesa_path.name),
                is_prompt_before_execute=True
            )
            if run_via_python:
                command_to_display = (
                    f'sudo chmod -R 755 {shlex.quote(str(new_iesa_output_abs_path))} && {shlex.quote(str(COPY_TO_UT_RUNNER_PATH))} '
                    f'--mode iesa '
                    f'--local_path {shlex.quote(str(new_iesa_output_abs_path))} '
                    f'--prompt_before_execute true'
                )
            display_content_to_copy(command_to_display, purpose="Copy IESA to target IP", is_copy_to_clipboard=True)
            append_build_log("Copy IESA command:")
            append_build_log(command_to_display)
        else:
            LOG(
                f"ERROR: Expected IESA artifact not found at '{OW_SW_OUTPUT_IESA_PATH}' or it's not a file.", file=sys.stderr)
            sys.exit(1)

    metadata_payload: Dict[str, Any] = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "build_type": build_type,
        "manifest_branch": ow_manifest_branch,
        # "original_iesa_md5": iesa_original_md5,
        "raw_arg_inputs": {k: v for k, v in vars(args).items()},
        "finalized_params": {
            "manifest_content": actual_manifest.to_serializable_dict(),
            "base_manifest_branch": base_manifest_branch,
            "tisdk_ref": tisdk_ref,
            "overridden_repos": repo_change_details,
            "repo_changes": repo_change_details,
        },
        "output_paths": {
            "binary_directory": str(OW_SW_BUILD_BINARY_OUTPUT_PATH),
            "iesa_artifact_path": str(iesa_artifact_path) if iesa_artifact_path else None,
            "manifest_path": str(MANIFEST_OUT_ARTIFACT_PATH),
            "log_path": str(LOG_OUT_PATH),
        },
    }

    write_build_metadata(metadata_payload)

# ───────────────────────────  helpers / actions  ─────────────────────── #


def setup_prebuild(build_type: str, manifest_source: str, ow_manifest_branch: str, base_manifest_branch: str, input_tisdk_ref: Optional[str], overwrite_repos: List[str], current_local_branch: str, tisdk_ref_from_ci_yml: Optional[str] = None) -> Tuple[IesaManifest, List[Dict[str, Any]]]:
    remove_tmp_build()
    
    ow_sw_path_str = str(OW_SW_PATH)
    # PRE-BUILD CHECK
    LOG(f"{MAIN_STEP_LOG_PREFIX} Pre-build check...")
    LOG("Checking OW branch is ahead/descendant of remote base manifest branch.")
    ow_git_remote = DEFAULT_OW_GIT_REMOTE
    ow_branch_is_descendant = git_is_local_branch_descendant_of_remote_branch(
        OW_SW_PATH, current_local_branch, base_manifest_branch, remote_name=ow_git_remote, fetch_remote=True)
    if not ow_branch_is_descendant:
        LOG_EXCEPTION_STR(
            f"ERROR: Current OW branch '{current_local_branch}' is not a descendant of '{ow_git_remote}/{base_manifest_branch}'.\n\n"
            f"This requirement is weird but exists because we run a docker command and mount OW_SW_PATH into the container "
            f"(docker run -it --rm -v $(pwd):$(pwd) <image>), so the OW branch must be in sync.\n\n"
            f"Fix suggestions:\n"
            f"- Rebase current branch: cd {ow_sw_path_str} && git fetch {ow_git_remote} && git rebase {ow_git_remote}/{base_manifest_branch}\n"
            f"- Or checkout a branch that already descends from {ow_git_remote}/{base_manifest_branch}"
        )
       
    LOG(f"Current OW branch '{current_local_branch}' is descendant of '{ow_git_remote}/{base_manifest_branch}'.")

    if build_type == BUILD_TYPE_IESA:
        if not input_tisdk_ref:
            LOG(f"ERROR: TISDK ref is not provided.", file=sys.stderr)
            sys.exit(1)

        if not tisdk_ref_from_ci_yml:
            LOG(f"ERROR: Unable to validate TISDK ref because CI manifest ref is unknown.", file=sys.stderr)
            sys.exit(1)

        LOG(f"Check TISDK ref {input_tisdk_ref} matches with {GITLAB_CI_YML_PATH}'s tisdk branch to avoid using wrong BSP")
        if input_tisdk_ref != tisdk_ref_from_ci_yml:
            is_descendant = is_tisdk_ref_descendant(tisdk_ref_from_ci_yml, input_tisdk_ref)
            if is_descendant:
                LOG(f"TISDK ref '{input_tisdk_ref}' differs from '{tisdk_ref_from_ci_yml}' but is ahead/descendant based on local '{IESA_TISDK_TOOLS_REPO_NAME}' history. Proceeding with caution.")
            else:
                LOG(f"ERROR: Argument TISDK ref '{input_tisdk_ref}' isn't a descendant of '{tisdk_ref_from_ci_yml}'.", file=sys.stderr)
                sys.exit(1)
        else:
            LOG(f"TISDK ref '{input_tisdk_ref}' matches with {GITLAB_CI_YML_PATH}'s tisdk branch '{tisdk_ref_from_ci_yml}'.")

    # Verify overwrite_repos
    if overwrite_repos:
        manifest: IesaManifest = parse_local_gl_iesa_manifest()
        for repo_name in overwrite_repos:
            if repo_name not in manifest.get_all_repo_names():
                LOG(
                    f"ERROR: Invalid overwrite repo name: {repo_name}\nAvailable repo names in manifest: {manifest.get_all_repo_names()}")
                sys.exit(1)

    # PRE-BUILD SETUP
    LOG(f"{MAIN_STEP_LOG_PREFIX} Pre-build setup...")
    # Sync other repos from manifest of REMOTE OW_SW
    manifest_snapshot_path = init_and_sync_from_remote(ow_manifest_branch, manifest_source=manifest_source,
                                                       use_current_ow_branch=True)

    # {repo → relative path from build folder}, use local as they should be the same
    actual_manifest: IesaManifest = parse_local_gl_iesa_manifest(manifest_snapshot_path)
    manifest_metadata_path = copy_manifest_for_metadata(manifest_snapshot_path)
    LOG(f"Manifest snapshot copied to '{manifest_metadata_path}' for metadata export.")
    repo_change_details: List[Dict[str, Any]] = []
    base_manifest = get_base_manifest_from_remote_branch(base_manifest_branch)
    ow_base_ref = git_get_remote_branch_ref(base_manifest_branch, ow_git_remote)
    
    # Collect OW repo changes
    ow_change_snapshot = collect_repo_changes(
        repo_name=IESA_OW_SW_TOOLS_REPO_NAME,
        repo_path=OW_SW_PATH,
        base_ref=ow_base_ref,
        relative_path_vs_tmp_build=EMPTY_STR_VALUE,
    )
    repo_change_details.append(ow_change_snapshot)
    # Collect other repos changes
    if overwrite_repos:
        # Copy local code to overwrite code from remote before build
        repo_names = [get_path_no_suffix(r, GIT_SUFFIX) for r in overwrite_repos]
        for repo_name in repo_names:
            repo_rel_path_vs_tmp_build = actual_manifest.get_repo_relative_path_vs_tmp_build(repo_name)
            if repo_name not in actual_manifest.get_all_repo_names():
                LOG(f"ERROR: Specified repo \"{repo_name}\" not found in manifest.", file=sys.stderr)
                sys.exit(1)
            override_fetched_repo_with_local_repo(repo_name, repo_rel_path_vs_tmp_build)

        change_snapshots: List[Dict[str, Any]] = []
        for repo_name in repo_names:
            rel_path = actual_manifest.get_repo_relative_path_vs_tmp_build(repo_name)
            if not rel_path:
                continue
            base_manifest_ref = base_manifest.get_repo_revision(repo_name)
            if not base_manifest_ref:
                LOG_EXCEPTION_STR("❌ FATAL: Base manifest ref is unknown for repo: " + repo_name)
            repo_info = LOCAL_REPO_MAPPING.get_by_name(repo_name)
            source_repo_path = repo_info.repo_local_path if repo_info else (OW_SW_BUILD_FOLDER_PATH / rel_path)
            resolved_base_ref = resolve_manifest_base_ref(source_repo_path, base_manifest_ref)
            change_snapshot = collect_repo_changes(
                repo_name=repo_name,
                repo_path=source_repo_path,
                base_ref=resolved_base_ref,
                relative_path_vs_tmp_build=rel_path,
            )
            change_snapshots.append(change_snapshot)

        any_changed: bool = any(snapshot.get("has_changes") for snapshot in change_snapshots)
        if not any_changed:
            LOG("WARNING: No files changed in selected repos.")
        repo_change_details.extend(change_snapshots)

    if build_type == BUILD_TYPE_IESA:
        prepare_iesa_bsp(input_tisdk_ref)

    return actual_manifest, repo_change_details


def run_build(build_type: str, interactive: bool, make_clean: bool = True, is_debug_build: bool = False) -> None:
    if build_type == BUILD_TYPE_BINARY:
        make_target = "arm"
    elif build_type == BUILD_TYPE_IESA:
        make_target = "package"
    else:
        LOG_EXCEPTION_STR(f"Unknown build type: {build_type}, expected {BUILD_TYPE_BINARY} or {BUILD_TYPE_IESA}")

    docker_image: str = get_docker_image_from_gitlab_ci(GITLAB_CI_YML_PATH)
    # docker_image: str = "oneweb_test:v1"
    LOG(f"Using Docker image: {docker_image}")
    docker_cmd_base = ( f"docker run -it --rm -v {OW_SW_PATH}:{OW_SW_PATH} -w {OW_SW_PATH} {docker_image}" )

    # Command to find and convert script files to Unix format
    dos2unix_cmd = (
        f"apt-get install -y dos2unix && "
        f"find {OW_SW_PATH.absolute()}/ \\( -name .git -o -name __pycache__ \\) " # -o -name tmp_build
        "-prune -o -type f \\( -name '*.py' -o -name '*.sh' -o -name '*.json' \\) -exec dos2unix {} +"
    )

    chmod_cmd = f"chmod -R +x {OW_SW_PATH.absolute()}/"

    time_start = datetime.now()
    bash_cmd_prefix = f"bash -c"
    make_clean_cmd = "make clean"
    debug_suffix = " DEBUG=1" if is_debug_build else ""
    if interactive:
        show_noti(title="Interactive Mode", message="Starting interactive mode...")
        LOG(f"{LINE_SEPARATOR}Entering interactive mode.")

        # Build the command sequence based on make_clean flag
        keep_interactive_shell = "exec bash"  # Keep container alive with an interactive shell after setup
        if make_clean:
            bash_cmd = f"""{bash_cmd_prefix} "echo 'Running dos2unix on script files...' && {dos2unix_cmd} && echo 'Granting execute permissions to script files...' && {chmod_cmd} && echo 'Cleaning build' && {make_clean_cmd} && echo -e '\\nTo start the {build_type} build, run the command below:\\n\\nmake {make_target}{debug_suffix}\\n\\nType exit or press Ctrl+D to leave interactive mode.' && {keep_interactive_shell}" """
        else:
            bash_cmd = f"""{bash_cmd_prefix} "echo 'Running dos2unix on script files...' && {dos2unix_cmd} && echo 'Granting execute permissions to script files...' && {chmod_cmd} && echo -e '\\nTo start the {build_type} build, run the command below:\\n\\nmake {make_target}{debug_suffix}\\n\\nType exit or press Ctrl+D to leave interactive mode.' && {keep_interactive_shell}" """

        run_shell(f"{docker_cmd_base} {bash_cmd}", check_LOG_EXCEPTION_STR_on_exit_code=False)
        LOG(f"Exiting interactive mode...")
    else:
        LOG("Running dos2unix on script files and build command...")

        # Build the command sequence based on make_clean flag
        if make_clean:
            bash_cmd = f"{bash_cmd_prefix} '{dos2unix_cmd} && {chmod_cmd} && {make_clean_cmd} && make {make_target}{debug_suffix}'"
        else:
            bash_cmd = f"{bash_cmd_prefix} '{dos2unix_cmd} && {chmod_cmd} && make {make_target}{debug_suffix}'"

        run_shell(f"{docker_cmd_base} {bash_cmd}")
        elapsed_time = (datetime.now() - time_start).total_seconds()
        LOG(f"Build finished in {elapsed_time} seconds", show_time=True)
        show_noti(title="Build finished", message=f"Build finished in {elapsed_time} seconds")


def remove_tmp_build() -> None:
    if OW_SW_BUILD_FOLDER_PATH.exists():
        LOG(f"Force removing tmp_build folder at {OW_SW_BUILD_FOLDER_PATH}...")
        # Move back to parent directory before removing tmp_build
        original_cwd = Path.cwd()
        if is_current_relative_to(Path.cwd(), OW_SW_BUILD_FOLDER_PATH):
            LOG(f"{LOG_PREFIX_MSG_WARNING} Current directory is inside tmp_build, changing to {OW_SW_PATH}...")
            os.chdir(OW_SW_PATH)
        else:
            LOG(f"Current directory {original_cwd} is outside tmp_build, no need to change directory.")
        clear_directory(OW_SW_BUILD_FOLDER_PATH, remove_dir_itself=True)
        OW_SW_BUILD_FOLDER_PATH.mkdir(parents=True)
    else:
        OW_SW_BUILD_FOLDER_PATH.mkdir(parents=True)


def get_ci_repo_refs_from_ci_yml(file_path: str) -> Dict[str, List[str]]:
    repo_refs: Dict[str, Set[str]] = {}
    with open(file_path, 'r') as f:
        ci_config = yaml.safe_load(f)

    for job_details in ci_config.values():
        if not isinstance(job_details, dict) or 'needs' not in job_details or not isinstance(job_details.get('needs'), list):
            continue

        for need in job_details['needs']:
            if not isinstance(need, dict):
                continue
            project = (need.get('project') or "").strip()
            ref = (need.get('ref') or "").strip()
            if not project or not ref:
                continue
            repo_info: Optional[IesaLocalRepoInfo] = LOCAL_REPO_MAPPING.get_by_gl_project_path(project)
            if not repo_info:
                continue
            if repo_info.repo_name not in repo_refs:
                repo_refs[repo_info.repo_name] = set()
            repo_refs[repo_info.repo_name].add(ref)

    return {repo_name: sorted(list(refs)) for repo_name, refs in repo_refs.items()}


def get_tisdk_ref_from_ci_yml(file_path: str) -> Optional[str]:
    ci_repo_refs = get_ci_repo_refs_from_ci_yml(file_path)
    tisdk_refs = ci_repo_refs.get(IESA_TISDK_TOOLS_REPO_NAME, [])
    if len(tisdk_refs) != 1:
        LOG(
            f"ERROR: Expected exactly 1 TISDK ref in CI config but got {tisdk_refs}.", file=sys.stderr)
        return None

    return tisdk_refs[0]


def init_and_sync_from_remote(manifest_repo_branch: str, manifest_source: str, use_current_ow_branch: bool, skip_repo_update=False) -> Path:
    LOG(f"{MAIN_STEP_LOG_PREFIX} Init and Sync repo at {OW_SW_BUILD_FOLDER_PATH}...")
    repo_root_for_manifest = str(OW_SW_PATH)
    if is_platform_windows():
        repo_root_for_manifest = convert_win_to_wsl_path(repo_root_for_manifest)
    manifest_repo_url = get_manifest_repo_url(manifest_source, repo_root_for_manifest)
    
    os.environ['REPO_SKIP_UPDATE'] = '1' # Skip repo update
    #if not skip_repo_update:
    #    _update_repo_if_needed()
    
    use_local_git_repo = True
    extra_repo_args = f" --repo-url={GIT_REPO_PATH} --repo-rev=v2.61" if use_local_git_repo else ""
    run_shell(f"repo init {manifest_repo_url} -b {manifest_repo_branch} -m {IESA_MANIFEST_RELATIVE_PATH}{extra_repo_args}", cwd=OW_SW_BUILD_FOLDER_PATH)

    # Construct the full path to the manifest file
    manifest_full_path = Path(OW_SW_BUILD_FOLDER_PATH / ".repo" / "manifests" / IESA_MANIFEST_RELATIVE_PATH)
    manifest_snapshot_content = ""
    # Check if the manifest file exists before trying to read it
    LOG("\n--------------------- MANIFEST ---------------------")
    if manifest_full_path.exists():
        LOG(f"--- Manifest Content ({manifest_full_path}) ---")
        manifest_snapshot_content = manifest_full_path.read_text(encoding="utf-8")
        LOG(manifest_snapshot_content)
        LOG("--- End Manifest Content ---")

        if manifest_source == MANIFEST_SOURCE_LOCAL and use_current_ow_branch:
            LOG("Using local current OW branch manifest, double-checking manifest content...")
            manifest_local_path = OW_SW_PATH / IESA_MANIFEST_RELATIVE_PATH
            if manifest_local_path.exists():
                # Compare content
                is_same: bool = is_same_xml(manifest_full_path, manifest_local_path)
                if not is_same:
                    # Check for uncommitted changes in the local manifest
                    git_diff_output = git_diff_on_file(OW_SW_PATH, "HEAD", IESA_MANIFEST_RELATIVE_PATH)
                    any_unstaged_manifest_change = bool(git_diff_output.strip())
                    LOG_EXCEPTION_STR(f"Actual manifest at {manifest_full_path} does not match with local manifest at {manifest_local_path}" + (
                        f', and there are uncommitted changes in local manifest below:\n{git_diff_output}\nCommit these changes with below command:\n cd {OW_SW_PATH} && git add {IESA_MANIFEST_RELATIVE_PATH} && git commit -m "Update manifest" ' if any_unstaged_manifest_change else f', check push lastet local branch {manifest_repo_branch} to remote if needed.'), exit=True)
            else:
                LOG_EXCEPTION_STR(f"Expected local manifest file not found at {manifest_local_path}.", exit=True)
            LOG("Local manifest content matches the synced manifest.")
    else:
        LOG_EXCEPTION_STR(f"Manifest file not found at: {manifest_full_path}")

    manifest: IesaManifest = parse_local_gl_iesa_manifest(manifest_full_path)
    if not manifest or not is_manifest_valid(manifest):
        LOG_EXCEPTION_STR("Parsed manifest is invalid or empty.")

    run_shell("repo sync", cwd=OW_SW_BUILD_FOLDER_PATH)
    return manifest_full_path


def get_base_manifest_from_remote_branch(base_manifest_branch: str) -> IesaManifest:
    remote_base_ref = git_get_remote_branch_ref(base_manifest_branch, DEFAULT_OW_GIT_REMOTE)
    if not git_check_ref(OW_SW_PATH, remote_base_ref, ref_name="base manifest branch on remote"):
        LOG(f"ERROR: Base manifest branch '{remote_base_ref}' is missing.", file=sys.stderr)
        sys.exit(1)
    manifest_git_obj = f"{remote_base_ref}:{IESA_MANIFEST_RELATIVE_PATH}"
    manifest_show = run_shell(
        [CMD_GIT, "show", manifest_git_obj],
        cwd=OW_SW_PATH,
        capture_output=True,
        text=True,
        check_throw_exception_on_exit_code=False,
    )
    manifest_content = manifest_show.stdout.strip()
    if manifest_show.returncode != 0 or not manifest_content:
        LOG(f"ERROR: Unable to read base manifest '{manifest_git_obj}'.", file=sys.stderr)
        sys.exit(1)
    return parse_remote_gl_iesa_manifest(manifest_content)


def resolve_manifest_base_ref(repo_path: Path, base_manifest_ref: str) -> str:
    normalized_ref = (base_manifest_ref or "").strip()
    if not normalized_ref:
        LOG(f"ERROR: Empty base manifest ref for repo '{repo_path}'.", file=sys.stderr)
        sys.exit(1)
    git_fetch_remote(repo_path, DEFAULT_OW_GIT_REMOTE)
    remote_branch_ref = git_get_remote_branch_ref(normalized_ref, DEFAULT_OW_GIT_REMOTE)
    if git_is_ref_or_branch_existing(repo_path, remote_branch_ref):
        return remote_branch_ref
    if git_is_ref_or_branch_existing(repo_path, normalized_ref):
        return normalized_ref
    LOG(
        f"ERROR: Cannot resolve required base ref '{normalized_ref}' (or '{remote_branch_ref}') in '{repo_path}'.",
        file=sys.stderr,
    )
    sys.exit(1)


def override_fetched_repo_with_local_repo(repo_name: str, repo_rel_path_vs_tmp_build: str) -> None:
    """Overwrite fetched repos from repo command with local code."""
    local_repo_info: Optional[IesaLocalRepoInfo] = LOCAL_REPO_MAPPING.get_by_name(repo_name)
    if not local_repo_info:
        LOG(f"ERROR: Could not find repo info for '{repo_name}'", file=sys.stderr)
        LOG_EXCEPTION_STR(f"Could not find repo info for '{repo_name}'")

    fetched_src_path = local_repo_info.repo_local_path
    dest_root_path = OW_SW_BUILD_FOLDER_PATH / repo_rel_path_vs_tmp_build

    if not fetched_src_path.is_dir() or not dest_root_path.is_dir():
        LOG(f"ERROR: Source or destination not found at {fetched_src_path} or {dest_root_path}", file=sys.stderr)
        LOG_EXCEPTION_STR(f"Source or destination not found at {fetched_src_path} or {dest_root_path}")

    LOG(f"Verifying git history for '{repo_name}'...")
    src_overwrite_commit = git_get_sha1_of_head_commit(fetched_src_path)
    LOG(f"Source commit to overwrite: {src_overwrite_commit}")
    dest_orig_commit = git_get_sha1_of_head_commit(dest_root_path)  # Fetch remotely via repo sync
    LOG(f"Destination (to be overwritten) commit: {dest_orig_commit}")
    if src_overwrite_commit == dest_orig_commit:
        LOG("Source and destination are at the same commit. No history check needed.")
    elif not git_is_ancestor(dest_orig_commit, src_overwrite_commit, cwd=local_repo_info.repo_local_path):
        LOG_EXCEPTION_STR(f"Overwrite commit ({str(local_repo_info.repo_local_path)}: {src_overwrite_commit}) is not a descendant of original commit ({str(dest_root_path)}: {dest_orig_commit}).\nMake sure to rebase the branch on top of dest branch (+ force push if need) in manifest fetched remotely via repo sync!")
    else:
        LOG(f"Common ancestor for '{repo_name}' found. Proceeding with sync.")

    LOG(f"Copying from \"{fetched_src_path}\" to \"{dest_root_path}\"")

    EXCLUDE_DIRS = {".git", ".vscode"}
    for file_or_dir in fetched_src_path.rglob("*"):
        # parts = [part1, part2, part3] if path is "part1/part2/part3"
        if any(part in EXCLUDE_DIRS for part in file_or_dir.parts):
            continue

        file_rel_path = file_or_dir.relative_to(fetched_src_path)
        dest_path = dest_root_path / file_rel_path
        if file_or_dir.is_file():
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            if not dest_path.exists() or is_diff_ignore_eol(file_or_dir, dest_path):
                shutil.copy2(file_or_dir, dest_path)
        elif file_or_dir.is_dir():
            # Create directories if they don't exist
            dest_path.mkdir(parents=True, exist_ok=True)


def collect_repo_changes(repo_name: str, repo_path: Path, base_ref: str, relative_path_vs_tmp_build: str = EMPTY_STR_VALUE) -> Dict[str, Any]:
    if not repo_path.exists():
        LOG(f"WARNING: Repo path '{repo_path}' not found when collecting changes for '{repo_name}'.")
        return {
            "repo_name": repo_name,
            "relative_path_vs_tmp_build": relative_path_vs_tmp_build,
            "expected_base_ref": base_ref,
            "actual_ref": None,
            "actual_commit": None,
            "expected_base_commit": None,
            "ref_relation_vs_base_ref": "repo_not_found",
            "ref_matches_base_ref": False,
            "status_lines": [],
            "has_changes": False,
            "diff_file_path": None,
        }

    changes: List[str] = git_get_porcelain_status_lines(repo_path)
    if changes:
        LOG(f"\nChanges in {repo_name}:")
        for line in changes:
            LOG(" ", line)
    else:
        LOG(f"\nNo changes detected in {repo_name}.")

    actual_ref = git_get_current_branch(repo_path) or "HEAD"
    actual_commit = git_resolve_ref_to_commit(repo_path, "HEAD")
    expected_base_commit = git_resolve_ref_to_commit(repo_path, base_ref)
    if not expected_base_commit:
        LOG(f"ERROR: Required base ref '{base_ref}' could not be resolved in '{repo_path}'.", file=sys.stderr)
        sys.exit(1)
    ref_relation_vs_base_ref = git_get_ref_relation(repo_path, base_ref, "HEAD")
    ref_matches_base_ref = bool(expected_base_commit and actual_commit and expected_base_commit == actual_commit)

    changed_files_base_vs_head: List[str] = git_get_changed_files_against_ref(repo_path, f"{base_ref}..HEAD")
    changed_files_base_vs_worktree: List[str] = git_get_changed_files_against_ref(repo_path, base_ref)
    LOG(f"Changed files vs {base_ref}..HEAD in '{repo_name}': {len(changed_files_base_vs_head)}")
    LOG(f"Changed files vs {base_ref} (worktree included) in '{repo_name}': {len(changed_files_base_vs_worktree)}")
    has_changes = bool(changed_files_base_vs_worktree) or bool(changes) or (ref_relation_vs_base_ref != "same_commit")
    diff_file_path = export_repo_diff_artifact(repo_name, repo_path, base_ref)

    return {
        "repo_name": repo_name,
        "relative_path_vs_tmp_build": relative_path_vs_tmp_build,
        "expected_base_ref": base_ref,
        "actual_ref": actual_ref,
        "actual_commit": actual_commit,
        "expected_base_commit": expected_base_commit,
        "ref_relation_vs_base_ref": ref_relation_vs_base_ref,
        "ref_matches_base_ref": ref_matches_base_ref,
        "status_lines": changes,
        "changed_files_base_vs_head": changed_files_base_vs_head,
        "changed_files_base_vs_worktree": changed_files_base_vs_worktree,
        "has_changes": has_changes,
        "diff_file_path": str(diff_file_path) if diff_file_path else None,
    }


def export_repo_diff_artifact(repo_name: str, repo_path: Path, base_ref: str) -> Optional[Path]:
    """
    Export the working tree diff for a repo that was overwritten into the temp output folder.
    """
    ensure_temp_build_output_dir()
    safe_repo_name = sanitize_str_to_file_name(repo_name) or repo_name
    diff_filename = f"{IESA_TEST_DIFF_PREFIX}{safe_repo_name}"
    diff_path = TEMP_OW_BUILD_OUTPUT_PATH / diff_filename
    diff_content = build_repo_change_artifact_content(repo_path, base_ref)
    if not diff_content:
        if diff_path.exists():
            diff_path.unlink()
        LOG(f"No diff content for '{repo_name}', skipping artifact export.")
        return None

    with open(diff_path, "w", encoding="utf-8") as diff_file:
        diff_file.write(diff_content + "\n")
    LOG(f"Saved diff for '{repo_name}' to '{diff_path}'.")
    return diff_path


def build_repo_change_artifact_content(repo_path: Path, base_ref: str) -> str:
    sections: List[str] = []
    base_to_head_result = run_shell([CMD_GIT, "diff", "--patch-with-stat", f"{base_ref}..HEAD"], cwd=repo_path, capture_output=True, text=True, check_throw_exception_on_exit_code=False)
    if base_to_head_result.returncode == 0 and base_to_head_result.stdout.strip():
        sections.append(f"### git diff --patch-with-stat {base_ref}..HEAD\n{base_to_head_result.stdout.strip()}")
    base_to_worktree_result = run_shell([CMD_GIT, "diff", "--patch-with-stat", base_ref], cwd=repo_path, capture_output=True, text=True, check_throw_exception_on_exit_code=False)
    if base_to_worktree_result.returncode == 0 and base_to_worktree_result.stdout.strip():
        sections.append(f"### git diff --patch-with-stat {base_ref}\n{base_to_worktree_result.stdout.strip()}")
    unstaged_diff = git_diff_worktree(repo_path).strip()
    if unstaged_diff:
        sections.append(f"### git diff (unstaged)\n{unstaged_diff}")
    staged_diff = git_diff_worktree(repo_path, ["--cached"]).strip()
    if staged_diff:
        sections.append(f"### git diff --cached\n{staged_diff}")
    untracked_result = run_shell([CMD_GIT, "ls-files", "--others", "--exclude-standard"], cwd=repo_path, capture_output=True, text=True, check_throw_exception_on_exit_code=False)
    if untracked_result.returncode == 0:
        untracked_lines = [line for line in untracked_result.stdout.splitlines() if line.strip()]
        if untracked_lines:
            sections.append("### git ls-files --others --exclude-standard\n" + "\n".join(untracked_lines))
    else:
        LOG(f"WARNING: Unable to list untracked files in '{repo_path}', git returned {untracked_result.returncode}.", file=sys.stderr)
    return "\n\n".join(sections).strip()


def git_get_changed_files_against_ref(repo_path: Path, diff_ref: str) -> List[str]:
    result = run_shell(
        [CMD_GIT, "diff", "--name-status", diff_ref],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check_throw_exception_on_exit_code=False,
    )
    if result.returncode != 0:
        LOG(f"WARNING: git diff --name-status {diff_ref} failed in '{repo_path}' with code {result.returncode}.", file=sys.stderr)
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def ensure_temp_build_output_dir() -> None:
    TEMP_OW_BUILD_OUTPUT_PATH.mkdir(parents=True, exist_ok=True)


def append_build_log(*values: object) -> None:
    ensure_temp_build_output_dir()
    with open(LOG_OUT_PATH, "a", encoding="utf-8") as log_file:
        LOG(*values, file=log_file, show_time=True, highlight=False)


def init_ow_build_log() -> None:
    ensure_temp_build_output_dir()
    write_to_file(str(LOG_OUT_PATH), "", mode=WriteMode.OVERWRITE) # overwrite with empty
    append_build_log("Build log started.")
    append_build_log(f"Log path: {LOG_OUT_PATH}")


def copy_manifest_for_metadata(manifest_source_path: Path) -> Path:
    ensure_temp_build_output_dir()
    manifest_metadata_path = MANIFEST_OUT_ARTIFACT_PATH
    source_resolved = manifest_source_path.resolve()
    dest_resolved = manifest_metadata_path.resolve()
    if source_resolved == dest_resolved:
        return manifest_metadata_path
    if manifest_metadata_path.exists():
        manifest_metadata_path.unlink()
    shutil.copy2(manifest_source_path, manifest_metadata_path)
    return manifest_metadata_path


def write_build_metadata(metadata_payload: Dict[str, Any]) -> Path:
    ensure_temp_build_output_dir()
    metadata_path = TEMP_OW_BUILD_OUTPUT_PATH / f"{IESA_METADATA_FILE}"
    with open(metadata_path, "w", encoding="utf-8") as metadata_file:
        json.dump(metadata_payload, metadata_file, indent=2)
    LOG(f"{MAIN_STEP_LOG_PREFIX} Build metadata saved to '{metadata_path}.")
    return metadata_path


def is_tisdk_ref_descendant(base_ref: str, candidate_descentdant_ref: str) -> bool:
    """
    Validate that `candidate_ref` is ahead of or equal to `base_ref` in the tisdk repo history.
    """
    repo_info = get_repo_info_by_name(IESA_TISDK_TOOLS_REPO_NAME)
    repo_path = repo_info.repo_local_path
    if not repo_path.exists():
        LOG(f"ERROR: Repo path '{repo_path}' for '{IESA_TISDK_TOOLS_REPO_NAME}' does not exist.", file=sys.stderr)
        return False

    # Ensure local refs are fresh before validation.
    fetch_success = git_fetch(repo_path)
    if not fetch_success:
        LOG(f"{LOG_PREFIX_MSG_WARNING} Failed to fetch latest refs for '{repo_path}'. Attempting to validate with existing refs.")

    missing_refs: List[str] = []
    for ref in (base_ref, candidate_descentdant_ref):
        if not git_is_ref_or_branch_existing(repo_path, ref):
            missing_refs.append(ref)

    if missing_refs:
        LOG(f"ERROR: Missing refs {missing_refs} in '{repo_path}'. Ensure the repository has these branches/tags locally.", file=sys.stderr)
        return False

    if git_is_ancestor(base_ref, candidate_descentdant_ref, cwd=repo_path):
        return True

    LOG(f"ERROR: TISDK ref '{candidate_descentdant_ref}' is not a descendant of '{base_ref}' in '{repo_path}'.", file=sys.stderr)
    return False


def get_manifest_repo_url(manifest_source: str, local_repo_path: str) -> Optional[str]:
    LOG(f"{MAIN_STEP_LOG_PREFIX} Getting manifest repo URL...")
    manifest_url: Optional[str] = None
    if manifest_source == MANIFEST_SOURCE_REMOTE:
        manifest_url = f"{GL_BASE_URL}/intellian_adc/oneweb_project_sw_tools"
    elif manifest_source == MANIFEST_SOURCE_LOCAL:
        manifest_url = f"file://{local_repo_path}"
    else:
        LOG_EXCEPTION_STR(
            f"Unknown manifest source: {manifest_source}, expected {MANIFEST_SOURCE_LOCAL} or {MANIFEST_SOURCE_REMOTE}")

    LOG(f"Using manifest source: {manifest_source} ({manifest_url})")
    return manifest_url


def prepare_iesa_bsp(tisdk_ref: str):
    LOG(f"{MAIN_STEP_LOG_PREFIX} Preparing IESA BSP for release, TISDK ref: {tisdk_ref}...")

    # Details of the target project and job
    target_job_name = "sdk_create_tarball_release"
    target_ref = tisdk_ref
    repo_info: IesaLocalRepoInfo = get_repo_info_by_name(IESA_TISDK_TOOLS_REPO_NAME)
    # Get the target project using the new function
    target_project = get_gl_project(repo_info=repo_info)

    # For robust fetching of branch names, consider get_all=True here too if you're not sure the default is sufficient.
    LOG(f"Target project: {repo_info.gl_project_path}, instance: {target_project.branches.list(get_all=True)[0].name}")

    pipeline_id = get_latest_successful_pipeline_id(target_project, target_job_name, target_ref)
    if not pipeline_id:
        LOG(f"No successful pipeline found for job '{target_job_name}' on ref '{target_ref}'.")
        sys.exit(1)

    artifacts_dir = BSP_ARTIFACT_FOLDER_PATH
    # Clean artifacts directory contents
    if os.path.exists(artifacts_dir):
        LOG(f"Cleaning artifacts directory: {artifacts_dir}")
        shutil.rmtree(artifacts_dir)

    paths: List[str] = download_job_artifacts(target_project, artifacts_dir, pipeline_id, target_job_name)
    if paths:
        bsp_path = None
        LOG(f"Artifacts extracted to: {artifacts_dir}")
        for path in paths:
            LOG(f"  {path}")
            file_name = os.path.basename(path)
            if file_name.startswith(BSP_ARTIFACT_PREFIX):
                if bsp_path:
                    LOG(f"Overwriting previous BSP path {bsp_path} with {path}")
                    LOG("Setting permissions for BSP file to 644...")
                    os.chmod(bsp_path, 0o644)  # 644: rw-r--r--
                bsp_path = path
        if bsp_path:
            LOG(f"Final BSP: {bsp_path}. md5sum: {get_file_md5sum(bsp_path)}")
            LOG(f"Creating symbolic link {BSP_SYMLINK_PATH_FOR_BUILD} -> {bsp_path}")
            subprocess.run(["ln", "-sf", bsp_path, BSP_SYMLINK_PATH_FOR_BUILD])
            subprocess.run(["ls", "-la", BSP_SYMLINK_PATH_FOR_BUILD])


# ───────────────────────  module entry-point  ────────────────────────── #
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        exception_trace = traceback.format_exc()
        LOG(f"ERROR: {exception_trace}", file=sys.stderr)
        show_noti(title="Error", message=f"An error occurred: {e}")
    except KeyboardInterrupt:
        LOG("\nAborted by user.", file=sys.stderr)
        sys.exit(1)
