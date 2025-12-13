import re
import os
import argparse
import matplotlib.pyplot as plt
from collections import defaultdict

# ==========================================
# 1. CONFIGURATION
# ==========================================

# Markers to identify lines
ITERATION_START_MARKER = "========== Iteration"

# Define the strings to look for in the log lines
GNSS_LINE = "GNSS fix_type reached '3D' in"
ANTENNA_LINE = "Antenna status reached 'good' in"
TN_CAL_START_LINE = "TN Cal status reached Coarse Search in"
MODEM_LINE = "Modem operating_mode reached 'online' in"
TN_CAL_DONE_LINE = "TN Cal status reached Completed in"
TN_OFFSET_LINE = "TN Offset ="
SINR_LINE = "SINR after TN calibration ="
APN_LINE = "APN Connection status reached"

# Format: (SEARCH_STRING, LEGEND_LABEL, Y_AXIS_UNIT)
LIST_OF_THINGS_TO_PLOT = [
    (GNSS_LINE, "GNSS Fix Time", "Seconds"),
    (ANTENNA_LINE, "Antenna Good Time", "Seconds"),
    (TN_CAL_START_LINE, "TN Cal Start", "Seconds"),
    (MODEM_LINE, "Modem Online", "Seconds"),
    (TN_CAL_DONE_LINE, "TN Cal Complete", "Seconds"),
    #(TN_OFFSET_LINE, "TN Offset", "Value"),
    #(SINR_LINE, "SINR", "dB"),
    (APN_LINE, "APN Connected", "Seconds")
]

# ==========================================
# 2. PARSING LOGIC
# ==========================================

def extract_number(line):
    """
    Extracts the last valid number (int or float) from a line.
    """
    matches = re.findall(r"[-+]?\d*\.\d+|\d+", line)
    if matches:
        return float(matches[-1])
    return None

def parse_log_file(filename):
    data_store = defaultdict(list)
    
    # Global counter. Increments every time we see "========== Iteration"
    global_sequence_id = 0
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            # enumerate(f, 1) gives us the line number starting at 1
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                
                # 1. Check for Iteration Header
                if ITERATION_START_MARKER in line:
                    global_sequence_id += 1
                    print(f"[Line {line_num}] Processing Iteration (Cumulative ID: {global_sequence_id})...")
                    continue
                    
                # 2. Extract Data if we have started at least one iteration
                if global_sequence_id > 0:
                    for search_str, label, _ in LIST_OF_THINGS_TO_PLOT:
                        if search_str in line:
                            val = extract_number(line)
                            
                            # Print process with Line Number
                            print(f"[Line {line_num}] Found '{label}': {val}")
                            
                            if val is not None:
                                data_store[label].append((global_sequence_id, val))
                                
    except Exception as e:
        print(f"Error reading file: {e}")
        return None

    return data_store

# ==========================================
# 3. PLOTTING LOGIC
# ==========================================

def plot_data(parsed_data, filename):
    if not parsed_data:
        print("No data found to plot. Please check your log file content.")
        return

    plt.figure(figsize=(14, 7))
    
    # Plot the Data Lines
    for _, label, unit in LIST_OF_THINGS_TO_PLOT:
        if label in parsed_data:
            points = parsed_data[label]
            points.sort(key=lambda x: x[0]) # Sort by sequence ID
            
            x_vals, y_vals = zip(*points)
            plt.plot(x_vals, y_vals, marker='o', markersize=4, linestyle='-', label=f"{label} ({unit})")

    plt.title(f"System Metrics: {os.path.basename(filename)}")
    plt.xlabel("Cumulative Iteration Count")
    plt.ylabel("Value")
    
    # Move legend outside if too crowded
    plt.legend(loc='upper right', bbox_to_anchor=(1.15, 1))
    
    plt.grid(True, linestyle='--', alpha=0.6)
    
    # Ensure X-axis uses integers
    ax = plt.gca()
    ax.xaxis.get_major_locator().set_params(integer=True)

    plt.tight_layout()
    
    # --- SAVE TO FILE ---
    # Construct output filename in the same directory as the input log
    log_dir = os.path.dirname(os.path.abspath(filename))
    output_filename = os.path.join(log_dir, "output_plot.png")
    
    try:
        plt.savefig(output_filename, dpi=300, bbox_inches='tight')
        print(f"Graph saved successfully to: {output_filename}")
    except Exception as e:
        print(f"Error saving graph image: {e}")
        
    # Show plot window as well (optional, you can remove plt.show() if you want headless only)
    # plt.show() 
    plt.close() # Close memory

# ==========================================
# 4. EXECUTION
# ==========================================
if __name__ == "__main__":
    # Setup Argument Parser
    parser = argparse.ArgumentParser(description="Plot system metrics from a log file.")
    parser.add_argument("-p", "--path", required=True, help="Path to the log file to be parsed")
    
    args = parser.parse_args()
    log_path = args.path

    # Check if file exists
    if os.path.exists(log_path):
        print(f"Reading file: {log_path}...")
        data = parse_log_file(log_path)
        
        if data:
            # Calculate total unique iterations found
            total_points = max(max(x[0] for x in vals) for vals in data.values())
            print(f"------------------------------------------------")
            print(f"Done. Found {total_points} cumulative iterations.")
            print(f"Generating plot...")
            plot_data(data, log_path)
    else:
        print(f"Error: The file '{log_path}' does not exist.")