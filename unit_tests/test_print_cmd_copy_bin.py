#!/home/vien/workspace/intellian_core_repos/local_tools/MyVenvFolder/bin/python
from dev.dev_common import *


# md5sum( OUTPUT_IESA_PATH )  # Ensure the path exists and is correct

# if OW_OUTPUT_IESA_PATH.is_file():

# Calculate MD5 checksum of the original file
# run_shell(f"sudo chmod 644 {new_iesa_output_abs_path}")
# original_md5 = md5sum(new_iesa_output_abs_path)
LOG("Use this below command to copy to target IP:\n")


command = (
    f'sudo chmod -R 755 {OW_SW_BUILD_BINARY_OUTPUT_PATH} && '
    f'while true; do '
    f'read -e -p "Enter binary path: " -i "{OW_SW_BUILD_BINARY_OUTPUT_PATH}/" BIN_PATH && '
    f'if [ -f "$BIN_PATH" ]; then break; else echo "Error: File $BIN_PATH does not exist. Please try again."; fi; '
    f'done && '
    f'BIN_NAME=$(basename "$BIN_PATH") && '
    f'DEST_NAME="$BIN_NAME" && '
    f'original_md5=$(md5sum "$BIN_PATH" | cut -d" " -f1) && '
    f'read -e -p "Enter target IP: " -i "192.168.10" TARGET_IP && '
    f'ping_acu_ip "$TARGET_IP" --mute && '
    f'scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -rJ root@$TARGET_IP "$BIN_PATH" root@192.168.100.254:/home/root/download/"$DEST_NAME" && '
    f'{{ '
    f'echo "SCP copy completed successfully"; '
    f'echo -e "Binary copied completed. Setup symlink on target UT $TARGET_IP with this below command:\\n"; '
    f'echo "actual_md5=\\$(md5sum /home/root/download/$DEST_NAME | cut -d\\" \\" -f1) && if [ \\"$original_md5\\" = \\"\\$actual_md5\\" ]; then echo \\"MD5 match! Proceeding...\\" && cp /opt/bin/$BIN_NAME /home/root/download/backup_$BIN_NAME && ln -sf /home/root/download/$DEST_NAME /opt/bin/$BIN_NAME && echo \\"Backup created and symlink updated: /opt/bin/$BIN_NAME -> /home/root/download/$DEST_NAME\\"; else echo \\"MD5 MISMATCH! Aborting.\\"; fi"; '
    f'}} || {{ '
    f'echo "SCP copy failed"; '
    f'}}'
)

command = wrap_cmd_for_bash(command)
display_content_to_copy(command, purpose="Copy BINARY to target IP", is_copy_to_clipboard=True)
