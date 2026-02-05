#!/home/vien/core_repos/local_tools/MyVenvFolder/bin/python
import shutil
from available_tools.iesa_tools.t_ow_local_build import IESA_EXEC_PATH, IESA_OUT_ARTIFACT_PATH, append_build_log, ensure_temp_build_output_dir, init_ow_build_log
from dev.dev_common import *
from dev.dev_iesa import *


def main() -> None:
    #if not OW_SW_OUTPUT_IESA_PATH.is_file():
    #    LOG(f"ERROR: Expected IESA artifact not found at '{OW_SW_OUTPUT_IESA_PATH}'.")
    #    return

    init_ow_build_log()
    new_iesa_path = IESA_OUT_ARTIFACT_PATH
    #ensure_temp_build_output_dir()
    #if new_iesa_path.exists():
    #    new_iesa_path.unlink()

    #shutil.move(str(OW_SW_OUTPUT_IESA_PATH), str(new_iesa_path))
    new_iesa_output_abs_path = new_iesa_path.resolve()
    #run_shell(f"sudo chmod +x {new_iesa_output_abs_path}")
    LOG(f"Renamed '{OW_SW_OUTPUT_IESA_PATH.name}' to '{new_iesa_path.name}'")
    LOG(f"Find output IESA here (WSL path): {new_iesa_output_abs_path}")
    append_build_log(f"IESA output path: {new_iesa_output_abs_path}")
    command_to_display = create_scp_ut_and_run_cmd(
        local_path=new_iesa_output_abs_path,
        exec_output_path=IESA_EXEC_PATH,
        remote_host="root@192.168.100.254",
        remote_dir="/home/root/download/",
        run_cmd_on_remote=f"iesa_umcmd install pkg {new_iesa_path.name} && tail -F /var/log/upgrade_log",
        is_prompt_before_execute=True
    )
    display_content_to_copy(command_to_display, purpose="Copy IESA to target IP", is_copy_to_clipboard=True)
    append_build_log("Copy IESA command:")
    append_build_log(command_to_display)
    append_build_log(f"IESA exec command path: {IESA_EXEC_PATH}")


if __name__ == "__main__":
    main()
