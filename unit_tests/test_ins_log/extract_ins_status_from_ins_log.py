#!/home/vien/local_tools/MyVenvFolder/bin/python
import re
import argparse

from dev_common import *

# The log data provided in your question
log_data = ""

parser = argparse.ArgumentParser(description="Extract unique insStatus values from a log file.")
parser.add_argument("file_path", help="Path to the log file")
args = parser.parse_args()

log_data=read_file_content(args.file_path)
# --- Script to extract unique insStatus values ---

# Use a list to preserve order and a set for efficient checking of duplicates
unique_statuses = []
seen_statuses = set()

# Regular expression to find "insStatus[...]" and capture the hex value
pattern = re.compile(r"insStatus\[(0x[0-9a-fA-F]+)\]")

# Iterate over each line in the log data
for line in log_data.strip().split('\n'):
    match = pattern.search(line)
    if match:
        # Extract the captured hex value (group 1)
        status = match.group(1)
        # If we haven't seen this status before, add it
        if status not in seen_statuses:
            seen_statuses.add(status)
            unique_statuses.append(status)

# Print the final result list
print(unique_statuses)