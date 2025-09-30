#!/home/vien/local_tools/MyVenvFolder/bin/python
from dev_common import *
from dev_iesa import *

new_iesa_path = OW_OUTPUT_IESA_PATH
new_iesa_name = new_iesa_path.name
new_iesa_output_abs_path = OW_OUTPUT_IESA_PATH

command = create_scp_ut_and_run_cmd(
    local_path=new_iesa_output_abs_path,
    remote_host="root@192.168.100.254",
    remote_dir="/home/root/download/",
    run_cmd_on_remote=f"iesa_umcmd install pkg {new_iesa_name} && tail -F /var/log/upgrade_log",
    is_prompt_before_execute=True
)
display_content_to_copy(command, purpose="Copy IESA to target IP", is_copy_to_clipboard=True)
