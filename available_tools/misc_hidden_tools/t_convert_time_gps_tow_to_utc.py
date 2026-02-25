#!/home/vien/workspace/intellian_core_repos/local_tools/MyVenvFolder/bin/python

from datetime import datetime, timedelta
import argparse # Import the argparse module for named command-line arguments
from pathlib import Path
from typing import List
from dev.dev_common.custom_structures import ToolData
from dev.dev_common.tools_utils import ToolTemplate, build_examples_epilog

def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="Convert GPS Time",
            extra_description="Convert GPS week and TOW to UTC",
            args={
                "--week": 2373,
                "--time_of_week_ms": 271835600,
            }
        ),
    ]

def calculate_gps_and_utc_time(week: int, time_of_week_ms: int, leap_seconds: int = 18):
    """
    Calculates GPS Week, GPS Week mod 1024, GPS Seconds of Week, GPS Time, and UTC Time.

    Args:
        week (int): The GPS week number.
        time_of_week_ms (int): The milliseconds into the GPS week.
        leap_seconds (int): The current number of leap seconds (default is 18 as of mid-2024).

    Returns:
        dict: A dictionary containing the calculated GPS and UTC time information.
    """

    # 1. GPS Week
    gps_week = week

    # 2. GPS Seconds of Week
    gps_seconds_of_week = time_of_week_ms / 1000.0

    # GPS epoch: January 6, 1980, 00:00:00 UTC
    # This is the reference point for GPS time.
    gps_epoch = datetime(1980, 1, 6, 0, 0, 0)

    # Calculate total seconds from GPS epoch to the given time
    # Each GPS week has 7 days * 24 hours/day * 3600 seconds/hour
    total_seconds_from_gps_epoch = (week * 7 * 24 * 3600) + gps_seconds_of_week

    # Add total seconds to GPS epoch to get the exact GPS time
    gps_time = gps_epoch + timedelta(seconds=total_seconds_from_gps_epoch)

    # Subtract leap seconds to convert GPS time to UTC time
    # UTC time lags behind GPS time by the number of accumulated leap seconds.
    utc_time = gps_time - timedelta(seconds=leap_seconds)

    return {
        "GPS Time": gps_time,
        "UTC Time": utc_time
    }


def getToolData() -> ToolData:
    return ToolData(tool_template=get_tool_templates())


# --- Example Usage ---
if __name__ == "__main__":
    # Create an ArgumentParser object
    parser = argparse.ArgumentParser(
        description="Calculate GPS and UTC time based on GPS week and time of week milliseconds."
    )
    parser.formatter_class = argparse.RawTextHelpFormatter
    # Fill help epilog from templates
    parser.epilog = build_examples_epilog(getToolData().tool_template, Path(__file__))
    # Add arguments for GPS week and time of week milliseconds
    parser.add_argument(
     "--week",
        type=int,
        required=True,
        help="The GPS week number."
    )
    parser.add_argument(
        "--time_of_week_ms",
        type=int,
        required=True,
        help="The milliseconds into the GPS week."
    )
    # You could also add --leap_seconds as an optional argument here if desired.

    # Parse the arguments provided by the user
    args = parser.parse_args()

    # Access the parsed arguments
    input_week = args.week
    input_time_of_week_ms = args.time_of_week_ms

    print(f"Calculating for GPS Week: {input_week}, Time of Week MS: {input_time_of_week_ms}\n")

    results = calculate_gps_and_utc_time(input_week, input_time_of_week_ms)

    for key, value in results.items():
        print(f"{key}: {value}")
