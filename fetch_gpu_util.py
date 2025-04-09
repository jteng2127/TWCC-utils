import json
import os
import requests
from requests.adapters import HTTPAdapter
from tqdm import tqdm
from urllib3.util.retry import Retry
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import curlify

from utils import ensure_timedelta, ensure_utc_datetime


class TWCCClient:
    def __init__(self, api_key):
        self.base_url = "https://apigateway.twcc.ai/api/v3/k8s-D-twcc"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "x-api-host": "k8s-D-twcc",
                "x-api-key": api_key,
            }
        )

        retry_strategy = Retry(
            total=5,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)

    def make_request(self, method, endpoint, params=None, data=None, json=None):
        url = f"{self.base_url}/{endpoint}"
        # print(f"Making {method} request to {url} with params: {params}")
        # print(f"Data: {data}, JSON: {json}")

        request = requests.Request(method, url, params=params, data=data, json=json)
        prepared = self.session.prepare_request(request)

        # print(f"[CURL]\n{curlify.to_curl(prepared)}\n")

        response = self.session.send(prepared)
        response.raise_for_status()
        return response.json()

    def get_project_id(self, project_name):
        data = self.make_request("GET", "projects/", params={"name": project_name})
        return data[0]["id"]

    def get_sites(self, project_id):
        data = self.make_request(
            "GET", "sites/", params={"project": project_id, "all_users": "1"}
        )
        return [
            {
                "id": item["id"],
                "name": item["name"],
                "create_time": item["create_time"],
                "user": {
                    "id": item["user"]["id"],
                    "username": item["user"]["username"],
                    "email": item["user"]["email"],
                    "display_name": item["user"]["display_name"],
                },
                "status": item["status"],
            }
            for item in data
        ]

    def get_pod_by_site(self, id):
        data = self.make_request("GET", f"sites/{id}/container/")

        public_ip = data["Service"][0]["public_ip"][0]
        ssh_port = None
        for port in data["Service"][0]["ports"]:
            if port["target_port"] == 22:
                ssh_port = port["port"]

        return {
            "public_ip": public_ip,
            "ssh_port": ssh_port,
            "pod_name": data["Pod"][0]["name"],
            "pod_status": data["Pod"][0]["status"],
            "pod_flavor": data["Pod"][0]["flavor"],
            "container": {
                "name": data["Pod"][0]["container"][0]["name"],
                "image": data["Pod"][0]["container"][0]["image"],
            },
        }

    def get_gpu_utilization_by_site(
        self,
        site_id,
        pod_name,
        end_time: datetime | str = None,
        time_window: str | timedelta = None,
    ):
        """
        Get GPU utilization of a specific pod.
        :param pod_name: Name of the pod.
        :param end_time: End time for the query (default: now).
        :param time_window: Time window for the query (default: 2 hours).
        :return: GPU utilization data. [{"gpu_util": "0.0", "timestamp": "2023-10-01T00:00:00Z", "unit": "%"}, ...]
        """
        end_time = ensure_utc_datetime(end_time)
        if end_time is None:
            end_time = datetime.now(timezone.utc)

        time_window = ensure_timedelta(time_window)
        if time_window is None:
            time_window = timedelta(hours=2)

        begin_time = (end_time - time_window).strftime("%Y-%m-%dT%H:%M:%SZ")
        end_time = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        return self.make_request(
            "GET",
            f"sites/{site_id}/container/gpu/",
            params={
                "begin_time": begin_time,
                "end_time": end_time,
                "pod_name": pod_name,
            },
        )


if __name__ == "__main__":
    load_dotenv()
    api_key = os.getenv("TWCC_API_KEY")
    project_name = os.getenv("TWCC_PROJECT_NAME")

    client = TWCCClient(api_key)

    project_id = client.get_project_id(project_name)
    print(f"Project ID: {project_id}")
    print(f"Project Name: {project_name}")

    sites = client.get_sites(project_id)
    print(f"Total sites (same as total container): {len(sites)}")

    gpu_utilization_per_user = {}
    for site_info in tqdm(sites, total=len(sites), bar_format="{l_bar}{bar:10}{r_bar}"):
        site_name = site_info["name"]
        site_id = site_info["id"]
        user_display_name = site_info["user"]["display_name"]

        if site_info["status"] != "Ready":
            print(f"Site {site_id} is not ready, skipping.")
            continue

        pod_info = client.get_pod_by_site(site_id)
        pod_name = pod_info["pod_name"]

        gpu_utilizations = client.get_gpu_utilization_by_site(
            site_id, pod_name, time_window="7 days"
        )

        if user_display_name not in gpu_utilization_per_user:
            gpu_utilization_per_user[user_display_name] = {}
        gpu_utilization_per_user[user_display_name][site_id] = gpu_utilizations

    # json_filename = (
    #     f"gpu_utilization_per_user-{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    # )
    json_filename = "gpu_utilization_per_user.json"
    with open(json_filename, "w", encoding="utf-8") as f:
        json.dump(
            gpu_utilization_per_user,
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"GPU utilization data saved to {json_filename}")
