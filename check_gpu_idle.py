from datetime import datetime
import json
import glob
import os

from utils import ensure_timedelta, ensure_utc_datetime


# def check_gpu_idle(gpu_utilizations, threshold_percentage=5.0, time_window=None):
#     """
#     Check if the GPU utilization is below a certain threshold for a given time window.
#     :param gpu_utilizations: List of GPU utilization data points.
#     :param threshold: Utilization threshold (default: 5.0%).
#     :param time_window: Time window from the end time (default: Full time range).
#     :return: True if idle, False otherwise.
#     """
#     start_time = None
#     end_time = None
#     for util_info in gpu_utilizations:
#         util_time = datetime.strptime(util_info["timestamp"], "%Y-%m-%dT%H:%M:%SZ")
#         if end_time is None or util_time > end_time:
#             end_time = util_time
#         if start_time is None or util_time < start_time:
#             start_time = util_time

#     time_window = ensure_timedelta(time_window)
#     if time_window is not None:
#         start_time = end_time - time_window

#     for util_info in gpu_utilizations:
#         util_time = datetime.strptime(util_info["timestamp"], "%Y-%m-%dT%H:%M:%SZ")
#         if util_time < start_time:
#             continue
#         if float(util_info["gpu_util"]) > threshold_percentage:
#             return False
#     return True


def get_max_idle_duration(gpu_utilizations, threshold_percentage=5.0):
    """
    Get the maximum idle duration of the GPU utilization, from the end time.
    :param gpu_utilizations: List of GPU utilization data points.
    :param threshold: Utilization threshold (default: 5.0%).
    :return: Maximum idle duration in timedelta format.
    """
    # sort, timestamp to datetime
    gpu_utilizations.sort(
        key=lambda x: ensure_utc_datetime(x["timestamp"]),
        reverse=True,
    )

    end_time = ensure_utc_datetime(gpu_utilizations[0]["timestamp"])
    idle_start_time = end_time
    for util_info in gpu_utilizations[1:]:
        util_time = ensure_utc_datetime(util_info["timestamp"])
        if float(util_info["gpu_util"]) > threshold_percentage:
            break
        idle_start_time = util_time
    return end_time - idle_start_time


if __name__ == "__main__":
    json_filename = "gpu_utilization_per_user.json"
    with open(json_filename, "r", encoding="utf-8") as f:
        gpu_utilization_per_user = json.load(f)

    for user_display_name, site_utilizations in gpu_utilization_per_user.items():
        print(f"User: {user_display_name}")
        for site_id, gpu_utilizations in site_utilizations.items():
            idle_duration = get_max_idle_duration(gpu_utilizations)
            print(f"  Site ID: {site_id}, Max Idle Duration: {idle_duration}")
