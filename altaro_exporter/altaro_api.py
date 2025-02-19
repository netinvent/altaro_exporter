#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of altaro_exporter

__appname__ = "altaro_exporter"
__author__ = "Orsiris de Jong"
__site__ = "https://www.github.com/netinvent/altaro_exporter"
__description__ = "Altaro API Prometheus data exporter"
__copyright__ = "Copyright (C) 2024-2025 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2024110501"

from ofunctions.requestor import Requestor
from ofunctions.misc import fn_name
from logging import getLogger
import time
import datetime
import requests
from prometheus_client import Summary, Gauge, Enum, REGISTRY

# from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily, REGISTRY

from altaro_exporter.__debug__ import _DEBUG


logger = getLogger()


class AltaroAPI:
    """
    Python bindings for Altaro API
    """

    def __init__(
        self,
        altaro_rest_host: str,
        altaro_rest_port: int = 36013,
        altaro_rest_path: str = "/api/rest",
        domain: str = None,
        username: str = None,
        password: str = None,
        cert_verify: bool = True,
        altaro_server_port: int = 36014,
        altaro_server_address: str = "LOCALHOST",
    ):
        if not domain:
            msg = "No Altaro domain given, using '.' by default"
            logger.warning(msg)
            self.domain = "."
        else:
            self.domain = domain
        if not altaro_rest_host:
            msg = "No Altaro REST API host given"
            logger.critical(msg)

        if not username:
            msg = "No Altaro username given"
            logger.critical(msg)

        if not password:
            msg = "No Altaro password given"
            logger.critical(msg)

        self.altaro_rest_host = altaro_rest_host
        self.altaro_rest_port = altaro_rest_port
        self.altaro_rest_path = altaro_rest_path
        self.username = username
        self.password = password
        self.cert_verify = cert_verify
        self.altaro_server_port = altaro_server_port
        self.altaro_server_address = altaro_server_address
        self.session_id = None

        self.req = Requestor(
            f"{self.altaro_rest_host}:{self.altaro_rest_port}",
            cert_verify=self.cert_verify,
            use_json=True,
        )
        self.req.api_session = requests.Session()
        self.req.connected_server = (
            f"https://{self.altaro_rest_host}:{self.altaro_rest_port}/"
        )
        # if not self.req.create_session(authenticated=False):
        #    msg = f"Cannot create session to {self.altaro_rest_host}"
        #    logger.critical(msg)
        #    raise ValueError(msg)
        self.req.endpoint = self.altaro_rest_path.strip("")

        # Register gauges

        self.gauge_altaro_api_success = Gauge(
            "altaro_api_success",
            "Altaro API request success 0 = success, 1 = cannot connect, 2 = api error",
        )

        self.gauge_lastbackup = Gauge(
            "altaro_lastbackup_timestamp",
            "Timestamp of last backup",
            ["vmname", "hostname", "vmuuid"],
        )
        self.gauge_lastoffsitecopy = Gauge(
            "altaro_lastoffsitecopy_timestamp",
            "Timestamp of last offsite copy",
            ["vmname", "hostname", "vmuuid"],
        )

        self.gauge_lastbackup_duration = Gauge(
            "altaro_lastbackup_duration_seconds",
            "Duration of last backup",
            ["vmname", "hostname", "vmuuid"],
        )
        self.gauge_lastoffsitecopy_duration = Gauge(
            "altaro_lastoffsitecopy_duration_seconds",
            "Duration of last offsite copy",
            ["vmname", "hostname", "vmuuid"],
        )

        self.gauge_lastbackup_transfersize_compressed = Gauge(
            "altaro_lastbackup_transfersize_compressed_bytes",
            "Compressed size of last backup",
            ["vmname", "hostname", "vmuuid"],
        )
        self.gauge_lastbackup_transfersize_uncompressed = Gauge(
            "altaro_lastbackup_transfersize_uncompressed_bytes",
            "Unompressed size of last backup",
            ["vmname", "hostname", "vmuuid"],
        )

        self.gauge_lastoffsitecopy_transfersize_compressed = Gauge(
            "altaro_lastoffsitecopy_transfersize_compressed_bytes",
            "Compressed size of last offsite copy",
            ["vmname", "hostname", "vmuuid"],
        )
        self.gauge_lastoffsitecopy_transfersize_uncompressed = Gauge(
            "altaro_lastoffsitecopy_transfersize_uncompressed_bytes",
            "Uncompressed size of last offsite copy",
            ["vmname", "hostname", "vmuuid"],
        )
        self.gauge_lastbackup_result = Gauge(
            "altaro_lastbackup_result",
            "Result of last backup 0 = success, 1 = warning, 2 = error, 3 = unknown, 4 = other errors",
            ["vmname", "hostname", "vmuuid"],
        )

        self.gauge_lastoffsitecopy_result = Gauge(
            "altaro_lastoffsitecopy_result",
            "Result of last offsite copy 0 = success, 1 = warning, 2 = error, 3 = unknown, 4 = other errors",
            ["vmname", "hostname", "vmuuid"],
        )

        # Create a metric to track time spent and requests made.
        REQUEST_TIME = Summary(
            "request_processing_seconds", "Time spent processing request"
        )

    def reset_vm_metrics(self):
        collectors = tuple(REGISTRY._collector_to_names.keys())
        for collector in collectors:
            try:
                collector._metrics.clear()
                collector._metric_init()
            except AttributeError:
                pass  # built-in collectors don't inherit from MetricsWrapperBase

    def authenticate(self, action: str = "login"):
        logger.info(
            f"Logging in as: {self.username} on server {self.altaro_server_address}:{self.altaro_server_port} via api {self.altaro_rest_host}:{self.altaro_rest_port}"
        )
        payload = {
            "ServerPort": self.altaro_server_port,
            "ServerAddress": self.altaro_server_address,
            "Username": self.username,
            "Password": self.password,
            "Domain": self.domain,
        }
        if action == "login":
            endpoint = self.req.endpoint + "/sessions/start"
        else:
            endpoint = self.req.endpoint + "/sessions/end"

        result = self.req.requestor(action="create", data=payload, endpoint=endpoint)
        if not result:
            try:
                logger.error(f"Request failed with: {result}")
                return False
            except AttributeError as exc:
                logger.error(f"No more info. Error code: {exc}")
                logger.debug("Trace:", exc_info=True)
                return False
        elif not result["Success"]:
            logger.error(
                f"Request succeed but response failed with: {result['ErrorMessage']}"
            )
            logger.warning(
                "This can happen if a session is already opened. Please wait 5 minutes for session to be closed by Altaro API"
            )
            return False
        else:
            if action == "login":
                logger.info("Session established")
                self.session_id = result["Data"]
            if action == "logout":
                logger.info("Session closed")
                self.session_id = None
        return result

    def _api_request(
        self, pre_endpoint: str, post_endpoint: str = "", action: str = "read"
    ):
        """
        Shorthand to logout / login if session is invalid
        """
        if not self.session_id:
            self.authenticate(action="login")
        result = self.req.requestor(
            endpoint=f"{pre_endpoint}{self.session_id}{post_endpoint}", action=action
        )
        if not result:
            # Let's try to logout, login just to make sure
            logger.warning("API call failed, trying to reauthenticate")
            self.authenticate(action="logout")
            self.authenticate(action="login")
            result = self.req.requestor(
                endpoint=f"{pre_endpoint}{self.session_id}{post_endpoint}",
                action=action,
            )
            if not result:
                logger.error(f"API call from {fn_name(1)} failed with: {result}")
                self.gauge_altaro_api_success.set(1)
                return False
        if not result["Success"]:
            if "Invalid Token" in result["ErrorMessage"]:
                self.authenticate(action="logout")
                self.authenticate(action="login")
                result = self.req.requestor(
                    endpoint=f"{pre_endpoint}{self.session_id}{post_endpoint}",
                    action="read",
                )
                if not result["Success"]:
                    logger.error(
                        f"API call from {fn_name(1)} succeed but response failed with: {result['ErrorMessage']}"
                    )
                self.gauge_altaro_api_success.set(2)
                return False
        self.gauge_altaro_api_success.set(0)
        return result

    def list_vms(
        self, include_unconfigured: bool = False, include_non_scheduled: bool = False
    ):
        result = self._api_request(
            pre_endpoint=f"/{self.altaro_rest_path}/vms/list/",
            post_endpoint="/1" if not include_unconfigured else "",
        )
        if result is False:
            logger.error("Could not list VMs")
            return False
        logger.info("VMs listed successfully")
        vms = result["VirtualMachines"]
        if not vms:
            logger.error("No VM data found in request:\n{vms}")
            return True

        for vm in vms:
            vmname = vm["VirtualMachineName"]
            hostname = vm["HostName"]
            vmuuid = vm["HypervisorVirtualMachineUuid"]
            is_scheduled = vm["NextBackupTime"] or vm["NextOffsiteCopyTime"]
            if not is_scheduled and not include_non_scheduled:
                logger.info(
                    f"Skipping VM {vmname} on {hostname} as it is not scheduled"
                )
                continue
            logger.info(f"Found VM {vmname} on {hostname}")

            # Last Backup, ex 2024-08-13-01-53-14
            LastBackupTime = vm["LastBackupTime"]
            if LastBackupTime:
                timestamp = float(
                    time.mktime(
                        datetime.datetime.strptime(
                            LastBackupTime, "%Y-%m-%d-%H-%M-%S"
                        ).timetuple()
                    )
                )
                self.gauge_lastbackup.labels(vmname, hostname, vmuuid).set(timestamp)

            # Last Offsite Copy
            LastOffsiteCopyTime = vm["LastOffsiteCopyTime"]
            if LastOffsiteCopyTime:
                timestamp = float(
                    time.mktime(
                        datetime.datetime.strptime(
                            LastOffsiteCopyTime, "%Y-%m-%d-%H-%M-%S"
                        ).timetuple()
                    )
                )
                self.gauge_lastoffsitecopy.labels(vmname, hostname, vmuuid).set(
                    timestamp
                )

            # LastBackupDuration in Seconds
            self.gauge_lastbackup_duration.labels(vmname, hostname, vmuuid).set(
                vm["LastBackupDuration"]
            )

            # LastOffsiteCopyDuration in Seconds
            self.gauge_lastoffsitecopy_duration.labels(vmname, hostname, vmuuid).set(
                vm["LastOffsiteCopyDuration"]
            )

            # LastOffsiteCopyTransferSizeCompressed in Bytes
            self.gauge_lastoffsitecopy_transfersize_compressed.labels(
                vmname, hostname, vmuuid
            ).set(vm["LastOffsiteCopyTransferSizeCompressed"])

            # LastOffsiteCopyTransferSizeUncompressed in Bytes
            self.gauge_lastoffsitecopy_transfersize_uncompressed.labels(
                vmname, hostname, vmuuid
            ).set(vm["LastOffsiteCopyTransferSizeUncompressed"])

            # LastBackupTransferSizeCompressed in Bytes
            self.gauge_lastbackup_transfersize_compressed.labels(
                vmname, hostname, vmuuid
            ).set(vm["LastBackupTransferSizeCompressed"])

            # LastBackupTransferSizeUncompressed in Bytes
            self.gauge_lastbackup_transfersize_uncompressed.labels(
                vmname, hostname, vmuuid
            ).set(vm["LastBackupTransferSizeUncompressed"])

            # LastBackupResult
            try:
                if vm["LastBackupResult"].lower() == "success":
                    last_backup_result = 0
                elif vm["LastBackupResult"].lower() == "warning":
                    last_backup_result = 1
                elif vm["LastBackupResult"].lower() == "error":
                    last_backup_result = 2
                elif vm["LastBackupResult"].lower() == "unknown":
                    last_backup_result = 3
                elif vm["LastBackupResult"] is not None:
                    last_backup_result = 4
                else:
                    last_backup_result = None
                if last_backup_result is not None:
                    self.gauge_lastbackup_result.labels(vmname, hostname, vmuuid).set(
                        last_backup_result
                    )
            except Exception as exc:
                logger.info(f"{vmname} has no last backup: {exc}")

            # LastOffsiteCopyResult
            try:
                if vm["LastOffsiteCopyResult"].lower() == "success":
                    last_offsite_backup_result = 0
                elif vm["LastOffsiteCopyResult"].lower() == "warning":
                    last_offsite_backup_result = 1
                elif vm["LastOffsiteCopyResult"].lower() == "error":
                    last_offsite_backup_result = 2
                elif vm["LastOffsiteCopyResult"].lower() == "unknown":
                    last_offsite_backup_result = 3
                elif vm["LastOffsiteCopyResult"] is not None:
                    last_offsite_backup_result = 4
                else:
                    last_offsite_backup_result = None
                if last_offsite_backup_result is not None:
                    self.gauge_lastoffsitecopy_result.labels(
                        vmname, hostname, vmuuid
                    ).set(last_offsite_backup_result)
            except Exception as exc:
                logger.info(f"{vmname} has no lastoffsitecopy: {exc}")
        return True


"""
This isn't launched unless for testing purposes

api = AltaroAPI(
    "https://localhost",
    usfername="Administrator",
    password="SomeTestPassword",
    cert_verify=False,
)
api.authenticate()
api.list_vms()
"""
