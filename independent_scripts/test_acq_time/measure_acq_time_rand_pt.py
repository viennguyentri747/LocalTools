#!/usr/bin/env python3
import requests
import time
import sys
import random
import json
import os
from threading import Thread

SSM_IP = None 
LOG_FILE = None

LOG_DIR_ROOT = "LOGS"
DEFAULT_ITERATIONS = 500
RANDOM_OFFSET_MIN = -180
RANDOM_OFFSET_MAX = 180
SLEEP_AFTER_TN_OFFSET = 3
SLEEP_AFTER_REBOOT = 3
ITERATION_SLEEP_INTERVAL = 5

REBOOT_RETRY_DELAY = 1
CHECK_INTERVAL = 1
GET_TN_OFFSET_RETRIES = 5
GET_TN_OFFSET_RETRY_DELAY = 1
TN_CAL_STATUS_POLL_INTERVAL = 1
APN_CHECK_INTERVAL = 1
DITHER_TRACKING_POLL_INTERVAL = 1
LOG_SINR_RETRY_DELAY = 1


def log(msg):
    timestamped_msg = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(timestamped_msg, flush=True)
    if LOG_FILE:
        with open(LOG_FILE, "a") as f:
            f.write(timestamped_msg + "\n")


def fail_and_exit(msg):
    log(f"FAILURE: {msg}")
    sys.exit(1)


def get_tn_offset(retries=GET_TN_OFFSET_RETRIES):
    for attempt in range(retries):
        try:
            response = requests.get(
                f"http://{SSM_IP}/aim/api/lui/data/config/antenna",
                headers={"Content-Type": "application/json"},
                timeout=5
            )
            response.raise_for_status()
            config = response.json()
            return float(config.get("dither_coarse_search_hypothesis0", 0))
        except (requests.RequestException, ValueError) as e:
            log(f"Attempt {attempt + 1}: Error reading TN Offset: {e}")
            time.sleep(GET_TN_OFFSET_RETRY_DELAY)
    fail_and_exit("Failed to read TN Offset after multiple retries")


def reboot_ssm():
    log("Sending reboot command to SSM...")
    while True:
        try:
            response = requests.get(f"http://{SSM_IP}/api/system/reboot", timeout=30)
            if response.status_code == 200:
                log("Reboot command sent successfully.")
                break
        except requests.RequestException:
            pass
        time.sleep(REBOOT_RETRY_DELAY)


def set_tn_offset(value):
    log(f"Setting TN Offset to {value}...")
    try:
        get_response = requests.get(
            f"http://{SSM_IP}/aim/api/lui/data/config/antenna",
            headers={"Content-Type": "application/json"},
            timeout=5
        )
        get_response.raise_for_status()
        config = get_response.json()
        config["dither_coarse_search_hypothesis0"] = str(value)

        post_response = requests.post(
            f"http://{SSM_IP}/aim/api/lui/data/config/antenna",
            headers={"Content-Type": "application/json"},
            data=json.dumps(config),
            timeout=5
        )
        post_response.raise_for_status()
        log("TN Offset updated successfully.")
    except requests.RequestException as e:
        fail_and_exit(f"Error communicating with SSM: {e}")


def wait_for_tn_cal_status(target_statuses):
    start_time = time.time()
    while True:
        try:
            response = requests.get(f"http://{SSM_IP}/aim/api/lui/data/status/antenna", timeout=3)
            response.raise_for_status()
            data = response.json()
            status = data.get("dither_coarse_search_status0", "")
            if status in target_statuses:
                elapsed = int(time.time() - start_time)
                log(f"TN Cal status reached {status} in {elapsed}s")
                return elapsed
        except (requests.RequestException, json.JSONDecodeError):
            pass
        time.sleep(TN_CAL_STATUS_POLL_INTERVAL)


def check_aps_connected(start_time):
    """Measure APN connection time from reboot start."""
    while True:
        try:
            response = requests.get(f"http://{SSM_IP}/api/modem/modemstatus", timeout=3)
            response.raise_for_status()
            data = response.json()
            status = data.get("apn_connection_status", [])
            if status == ["connected", "connected"]:
                elapsed = int(time.time() - start_time)
                log(f"APN Connection status reached {status} in {elapsed}s")
                return elapsed
        except (requests.RequestException, json.JSONDecodeError):
            pass
        time.sleep(APN_CHECK_INTERVAL)


def wait_for_status(url, key, target_value, description, result_dict, result_key):
    start_time = time.time()
    while True:
        try:
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                time.sleep(CHECK_INTERVAL)
                continue

            data = response.json()
            value = data
            for k in key.split('.'):
                if not isinstance(value, dict) or k not in value:
                    value = None
                    break
                value = value[k]

            if value == target_value:
                elapsed = int(time.time() - start_time)
                result_dict[result_key] = elapsed
                log(f"{description} reached '{target_value}' in {elapsed}s")
                return

        except (requests.RequestException, ValueError):
            pass
        time.sleep(CHECK_INTERVAL)


def log_sinr(retry_delay=LOG_SINR_RETRY_DELAY):
    """Log SINR after TN calibration is complete, retrying until successful."""
    while True:
        try:
            response = requests.get(f"http://{SSM_IP}/api/modem/lte_signal_info", timeout=5)
            response.raise_for_status()
            data = response.json()
            sinr = data.get("sinr_dB", None)
            if sinr is not None:
                log(f"SINR after TN calibration = {sinr} dB")
                return sinr
        except (requests.RequestException, ValueError) as e:
            pass
        time.sleep(retry_delay)


def wait_for_dither_tracking(result_dict, result_key, start_time):
    """Wait until dither_program_tracking0 becomes True after APN connection."""
    while True:
        try:
            response = requests.get(f"http://{SSM_IP}/aim/api/lui/data/status/antenna", timeout=3)
            response.raise_for_status()
            data = response.json()
            tracking = data.get("dither_program_tracking0", "False")
            if tracking == "True":
                elapsed = int(time.time() - start_time)
                result_dict[result_key] = elapsed
                log(f"ProgramTracking reached True in {elapsed}s")
                return
        except (requests.RequestException, json.JSONDecodeError):
            pass
        time.sleep(DITHER_TRACKING_POLL_INTERVAL)


def compute_stats(times_list):
    if not times_list:
        return 0, 0, 0
    return min(times_list), max(times_list), sum(times_list) / len(times_list)


def print_summary(total_times, component_times, count):
    """Helper function to print the running summary."""
    log(f"\n========== Summary (After {count} Iterations) ==========")
    best_total, worst_total, avg_total = compute_stats(total_times)
    log(f"Total iteration time -> Best: {best_total}s | Worst: {worst_total}s | Avg: {avg_total:.2f}s")

    for comp, times in component_times.items():
        if times:
            best, worst, avg = compute_stats(times)
            log(f"{comp.upper()} -> Best: {best}s | Worst: {worst}s | Avg: {avg:.2f}s")
    log("========================================================")


def main():
    # Usage check: Require at least script name, IP, and Output Folder
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <SSM_IP> <OUTPUT_FOLDER_NAME> [number_of_iterations]")
        print("Example: ./test.py 192.168.100.56 my_test_run")
        print("Example: ./test.py 192.168.100.56 daily_sanity 100")
        sys.exit(1)

    global SSM_IP, LOG_FILE
    
    # Arg 1: SSM IP (Mandatory)
    SSM_IP = sys.argv[1]

    # Arg 2: Output Folder Name (Mandatory)
    user_output_folder = sys.argv[2]

    # --- LOGGING SETUP ---
    # Construct base directory: LOGS/<user_input>
    log_dir = os.path.join(LOG_DIR_ROOT, user_output_folder)
    
    # Create directory if it doesn't exist
    os.makedirs(log_dir, exist_ok=True)
    
    # Construct Filename: LOGS/<user_input>/<IP>_log.txt
    LOG_FILE = os.path.join(log_dir, f"{SSM_IP.replace('.', '_')}_log.txt")
    # ---------------------

    # Arg 3: Iterations (Optional, default 50)
    iterations = DEFAULT_ITERATIONS
    if len(sys.argv) >= 4:
        try:
            iterations = int(sys.argv[3])
        except ValueError:
            print("Error: number_of_iterations must be an integer.")
            sys.exit(1)
    
    log(f"Starting test on SSM IP: {SSM_IP}")
    log(f"Iterations: {iterations}")
    log(f"Logging to: {LOG_FILE}")

    total_times = []
    component_times = {
        "antenna": [],
        "gnss": [],
        "modem": [],
        "tn_cal_start": [],
        "tn_cal_complete": [],
        "apn": [],
        "program_track": []
    }

    for i in range(1, iterations + 1):
        log(f"\n========== Iteration {i} of {iterations} ==========")

        random_offset = random.randint(RANDOM_OFFSET_MIN, RANDOM_OFFSET_MAX)
        set_tn_offset(random_offset)

        time.sleep(SLEEP_AFTER_TN_OFFSET)

        reboot_ssm()

        time.sleep(SLEEP_AFTER_REBOOT)
        reboot_start = time.time()

        # ----------------------------
        # PHASE 1: Start all except APN
        # ----------------------------
        results = {}
        threads = [
            Thread(target=wait_for_status, args=(
                f"http://{SSM_IP}/api/antenna/antennainfo",
                "status",
                "good",
                "Antenna status",
                results,
                "antenna"
            )),
            Thread(target=wait_for_status, args=(
                f"http://{SSM_IP}/api/gnss/gnssstats",
                "nmea_data.fix_type",
                "3D",
                "GNSS fix_type",
                results,
                "gnss"
            )),
            Thread(target=wait_for_status, args=(
                f"http://{SSM_IP}/api/modem/modemstatus",
                "operating_mode",
                "online",
                "Modem operating_mode",
                results,
                "modem"
            )),
        ]

        tn_start_thread = Thread(target=lambda: results.update({
            "tn_cal_start": wait_for_tn_cal_status(["Coarse Search", "Coarse Search Ex"])
        }))
        tn_complete_thread = Thread(target=lambda: results.update({
            "tn_cal_complete": wait_for_tn_cal_status(["Stopped", "Completed"])
        }))

        threads.extend([tn_start_thread, tn_complete_thread])

        for t in threads:
            t.start()

        # Wait until TN calibration completes
        tn_complete_thread.join()

        # Log current TN Offset
        current_offset = get_tn_offset()
        log(f"TN Offset = {current_offset}")

        # Log SINR after TN calibration
        sinr = log_sinr()        

        # ----------------------------
        # PHASE 2: Start APN and Dither tracking checks
        # ----------------------------
        apn_thread = Thread(target=lambda: results.update({"apn": check_aps_connected(reboot_start)}))
        # dither_thread = Thread(target=lambda: wait_for_dither_tracking(results, "program_track", reboot_start))     

        apn_thread.start()
        # dither_thread.start()

        # Wait for all threads
        for t in threads:
            t.join()
        apn_thread.join()
        # dither_thread.join()

        total_elapsed = int(time.time() - reboot_start)
        total_times.append(total_elapsed)
        for key in component_times.keys():
            component_times[key].append(results.get(key, 0))

        log(f"Iteration {i} complete: Total time = {total_elapsed}s")
        
        # Calculate and print summary after every iteration
        print_summary(total_times, component_times, i)

        time.sleep(ITERATION_SLEEP_INTERVAL)

    log("All iterations completed successfully!")


if __name__ == "__main__":
    main()
