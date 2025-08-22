#!/usr/bin/env python3
from dev_common import *


OW_SW_PATH = Path.home() / "ow_sw_tools/"
OUTPUT_IESA_PATH = OW_SW_PATH / "v_TEST_MANP-268_Support-Fan-On-Temp-Config-For-Fan-Via-Api.iesa"
# md5sum( OUTPUT_IESA_PATH )  # Ensure the path exists and is correct

if OUTPUT_IESA_PATH.is_file():
	new_iesa_path = OUTPUT_IESA_PATH
	new_iesa_name = OUTPUT_IESA_PATH.name
	# In linux, rename will overwrite.
	OUTPUT_IESA_PATH.rename(new_iesa_path)
	LOG(f"Renamed '{OUTPUT_IESA_PATH.name}' to '{new_iesa_path.name}'")
	LOG(f"Find output IESA here (WSL path): {new_iesa_path.resolve()}")
	LOG(f"{LINE_SEPARATOR}")
	output_path = new_iesa_path.resolve()
	new_iesa_output_abs_path = output_path
	# Calculate MD5 checksum of the original file
	# run_shell(f"sudo chmod 644 {new_iesa_output_abs_path}")
	# original_md5 = md5sum(new_iesa_output_abs_path)
	LOG("Use this below command to copy to target IP:\n")
	LOG(
		f'output_path="{new_iesa_output_abs_path}" '
		'&& read -e -i "192.168.10" -p "Enter source IP address: " source_ip '
		'&& rmh '
		'&& sudo chmod 644 "$output_path" '
		'&& scp -rJ root@$source_ip "$output_path" root@192.168.100.254:/home/root/download/ '
		'&& original_md5=$(md5sum "$output_path" | cut -d" " -f1) '
		'&& noti '
		'&& echo -e "IESA copied completed. Install on target UT $source_ip with this below command:\\n"'
		f'&& echo "original_md5=\\"$original_md5\\"; actual_md5=\\$(md5sum /home/root/download/{new_iesa_name} | cut -d\\\" \\\" -f1); echo \\\"original md5sum: \\$original_md5\\\"; echo \\\"actual md5sum: \\$actual_md5\\\"; if [ \\\"\\$original_md5\\\" = \\\"\\$actual_md5\\\" ]; then echo \\\"MD5 match! Install? y/n\\\"; read -r confirm; [ \\\"\\$confirm\\\" = \\\"y\\\" -o \\\"\\$confirm\\\" = \\\"Y\\\" ] && echo \\\"Installing...\\\" && iesa_umcmd install pkg {new_iesa_name} && tail -F /var/log/upgrade_log; else echo \\\"MD5 MISMATCH! Not installing.\\\"; fi"', show_time=False
	)