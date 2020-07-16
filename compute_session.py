from functools import lru_cache
from functools import wraps
from os import getenv

import requests
from google.auth import app_engine
from google.oauth2 import service_account
from googleapiclient import discovery

FIREWALL_RULE_NAME = "temporary-compute-session-handle"


def is_app_engine_environment():
    return getenv("SERVER_SOFTWARE", "").startswith("Google App Engine/")


def self_ip():
    return requests.get("https://checkip.amazonaws.com/").text.strip()


class ComputeSessionException(Exception):
    def __init__(self, message, exception):
        self.message = message
        self.exception = exception

    def __str__(self):
        return f"ComputeSessionException: {self.message}\n{self.exception}"


def throwable(message):
    def throwable(f):
        @wraps(f)
        def wrapper(*args, **kwds):
            try:
                return f(*args, **kwds)
            except Exception as inst:
                raise ComputeSessionException(message, inst)

        return wrapper

    return throwable


class ComputeSession:
    @throwable(
        "Failed to determine the remote IP address associated with the given network tag!"
    )
    @lru_cache
    def remote_ip(self):
        aggregated_instance_response = (
            self.compute_api.instances()
            .aggregatedList(project=self.project_id)
            .execute()
        )
        all_instances = [
            instance
            for regions in aggregated_instance_response["items"].values()
            for instance in regions.get("instances", [])
        ]
        eligible_instances = [
            instance
            for instance in all_instances
            if instance["status"] == "RUNNING"
            and self.remote_network_tag in instance["tags"]["items"]
        ]
        if not eligible_instances:
            raise Exception(
                f"No running compute instances with the network tag {self.remote_network_tag} were found!"
            )
        eligible_ips = [
            access_config["natIP"]
            for instance in eligible_instances
            for network_interface in instance["networkInterfaces"]
            for access_config in network_interface["accessConfigs"]
            if access_config["name"] == "External NAT"
        ]
        if not eligible_ips:
            raise Exception(f"No external IP addresses were found!")
        return eligible_ips[0]

    def __init__(self, remote_network_tag):
        auth_scopes = [
            "https://www.googleapis.com/auth/cloud-platform",
            "https://www.googleapis.com/auth/compute",
            "https://www.googleapis.com/auth/compute.readonly",
        ]
        credentials = (
            app_engine.Credentials(scopes=auth_scopes)
            if is_app_engine_environment()
            else service_account.Credentials.from_service_account_file(
                getenv("GOOGLE_APPLICATION_CREDENTIALS", "service-account.json"),
                scopes=auth_scopes,
            )
        )
        self.compute_api = discovery.build("compute", "v1", credentials=credentials)
        self.project_id = credentials.project_id
        self.remote_network_tag = remote_network_tag

    @throwable("Failed to add/update session firewall rule to allow this connection!")
    def __enter__(self):
        existing_rule = next(
            iter(
                self.compute_api.firewalls()
                .list(project=self.project_id, filter=f'name = "{FIREWALL_RULE_NAME}"')
                .execute()
                .get("items", [])
            ),
            None,
        )
        config = {
            "priority": 1000,
            "direction": "INGRESS",
            "sourceRanges": [f"{self_ip()}/32"],
            "sourceServiceAccounts": [],
            "description": f"Temporary handle to {self.remote_network_tag} compute session instance.",
            "destinationRanges": [],
            "sourceTags": [],
            "allowed": [{"IPProtocol": "tcp", "ports": ["4444"]}],
            "logConfig": {"enable": True},
            "disabled": False,
            "network": "global/networks/default",
            "targetServiceAccounts": [],
            "targetTags": [self.remote_network_tag],
            "denied": [],
            "name": FIREWALL_RULE_NAME,
        }
        if existing_rule:
            self.compute_api.firewalls().patch(
                project=self.project_id, firewall=FIREWALL_RULE_NAME, body=config
            ).execute()
        else:
            self.compute_api.firewalls().insert(
                project=self.project_id, body=config
            ).execute()
        return self

    @throwable("Failed to disable session firewall rule!")
    def __exit__(self, type, value, tb):
        self.compute_api.firewalls().patch(
            project=self.project_id,
            firewall=FIREWALL_RULE_NAME,
            body={"disabled": True},
        ).execute()
