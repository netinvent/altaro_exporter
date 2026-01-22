#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of altaro_exporter

__appname__ = "altaro_exporter"
__author__ = "Orsiris de Jong"
__site__ = "https://www.github.com/netinvent/altaro_exporter"
__description__ = "Altaro API Prometheus data exporter"
__copyright__ = "Copyright (C) 2024-2026 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2026012201"

import logging
import time
import datetime
import requests
from prometheus_client import Summary, Gauge, Enum, REGISTRY
from ofunctions.requestor import Requestor
from ofunctions.misc import fn_name

# from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily, REGISTRY

from altaro_exporter.__debug__ import _DEBUG

logger = logging.getLogger()


class AltaroAPI:
    """
    Python bindings for Altaro API
    """

    def __init__(
        self,
        altaro_rest_host: str = "localhost",
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
            "Duration of last backup in seconds",
            ["vmname", "hostname", "vmuuid"],
        )
        self.gauge_lastoffsitecopy_duration = Gauge(
            "altaro_lastoffsitecopy_duration_seconds",
            "Duration of last offsite copy in seconds",
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

        self.gauge_lastrestore_result = Gauge(
            "altaro_lastrestore_result",
            "Result of last restore operation  0 = success, 1 = warning, 2 = error, 3 = unknown, 4 = Aborted, 5 = other errors",
            ["vmname", "vmuuid"],
        )

        self.gauge_lastrestore = Gauge(
            "altaro_lastrestore_timestamp",
            "Timestamp of last restore operation",
            ["vmname", "vmuuid"],
        )

        self.gauge_lastrestore_duration = Gauge(
            "altaro_lastrestore_duration_seconds",
            "Duration of last backup in seconds",
            ["vmname", "vmuuid"],
        )

        # Create a metric to track time spent and requests made.
        REQUEST_TIME = Summary(
            "request_processing_seconds", "Time spent processing request"
        )

    @staticmethod
    def mktimestamp(date_string):
        return float(
            time.mktime(
                datetime.datetime.strptime(date_string, "%Y-%m-%d-%H-%M-%S").timetuple()
            )
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
        self,
        pre_endpoint: str,
        post_endpoint: str = "",
        action: str = "read",
        ignore_session_id: bool = False,
    ):
        """
        Shorthand to logout / login if session is invalid
        """
        if not self.session_id:
            self.authenticate(action="login")
        if ignore_session_id:
            endpoint = f"{pre_endpoint}{post_endpoint}"
        else:
            endpoint = f"{pre_endpoint}{self.session_id}{post_endpoint}"
        logger.debug(f"Requesting {endpoint}")
        result = self.req.requestor(endpoint=endpoint, action=action)
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

    def protocol_version(self):
        result = self._api_request(
            pre_endpoint=f"/{self.altaro_rest_path}/protocol/version",
            ignore_session_id=True,
        )
        if result is False:
            logger.error("Could not get API protocol version")
            return False
        logger.info(f"Using API protocol version {result}")
        return True

    def vm_restore_history(
        self,
        vmid: str,
        vmuuid: str,
        vmname: str,
    ):
        """
        Gives restore reports like
        {'RestoreReports': [{'DateTime': '2026-01-22-14-48-04', 'Duration': 1132, 'Result': 'Aborted', 'Location': '\\\\UNCPATH\\altaro', 'Error': 'The restore operation was aborted by the user. (ALTERR_BASERESTORECONTROLLER_007)', 'RestoreAsName': 'SomeVM-Clone-2026-01-22 14-34'}], 'Success': True, 'ErrorCode': None, 'ErrorMessage': None, 'ErrorAdditionalDetails': None}
        """

        result = self._api_request(
            pre_endpoint=f"/{self.altaro_rest_path}/reports/restore/",
            post_endpoint=f"/{vmid}",
        )
        if result is False:
            logger.error(f"Could not get VM restore history for {vmname} {vmid}")
            return False
        logger.info(f"Got VM restore history for {vmname} {vmid}")
        restore_status = 3
        try:
            restore_report = result["RestoreReports"]
        except KeyError:
            logger.error("Could not find any restore reports")
            return False

        restore_report = sorted(
            restore_report, key=lambda x: self.mktimestamp(x["DateTime"])
        )
        if not restore_report:
            return True
        logger.debug(f"Restore report for {vmname}\n{restore_report}")
        try:
            if restore_report[-1]["Result"].lower() == "success":
                restore_status = 0
            elif restore_report[-1]["Result"].lower() == "warning":
                restore_status = 1
            elif restore_report[-1]["Result"].lower() == "error":
                restore_status = 2
            elif restore_report[-1]["Result"].lower() == "unknown":
                restore_status = 3
            elif restore_report[-1]["Result"].lower() == "aborted":
                restore_status = 4
            elif restore_report[-1]["Result"].lower() is not None:
                restore_status = 5
            timestamp = self.mktimestamp(restore_report[-1]["DateTime"])
            duration = int(restore_report[-1]["Duration"])
        except IndexError:
            logger.error(f"No restore status available for {vmname} {vmuuid}")
            return False

        self.gauge_lastrestore_result.labels(vmname, vmuuid).set(restore_status)
        self.gauge_lastrestore.labels(vmname, vmuuid).set(timestamp)

        try:
            #  in Seconds
            self.gauge_lastrestore_duration.labels(vmname, vmuuid).set(duration)
        except KeyError:
            logger.error(f"Cannot get restore duration for {vmname}")
        return True

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
        logger.debug(f"Result:\n{result}")

        vms = result["VirtualMachines"]
        if not vms:
            logger.error("No VM data found in request:\n{vms}")
            return True

        for vm in vms:
            vmname = vm["VirtualMachineName"]
            hostname = vm["HostName"]
            vmuuid = vm["HypervisorVirtualMachineUuid"]
            vmid = vm["AltaroVirtualMachineRef"]
            is_scheduled = vm["NextBackupTime"] or vm["NextOffsiteCopyTime"]
            if not is_scheduled and not include_non_scheduled:
                logger.info(
                    f"Skipping VM {vmname} on {hostname} as it is not scheduled"
                )
                continue
            logger.info(f"Found VM {vmname} on {hostname}")

            self.vm_restore_history(vmid, vmuuid, vmname)

            # Last Backup, ex 2024-08-13-01-53-14
            LastBackupTime = vm["LastBackupTime"]
            if LastBackupTime:
                timestamp = self.mktimestamp(LastBackupTime)
                self.gauge_lastbackup.labels(vmname, hostname, vmuuid).set(timestamp)

            # Last Offsite Copy
            LastOffsiteCopyTime = vm["LastOffsiteCopyTime"]
            if LastOffsiteCopyTime:
                timestamp = self.mktimestamp(LastOffsiteCopyTime)
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


# This isn't launched unless for testing purposes
if __name__ == "__main__":
    logging.basicConfig(
        format="%(levelname)s:%(message)s", encoding="utf-8", level=logging.DEBUG
    )
    logger = logging.getLogger()

    api = AltaroAPI(
        username="Administrator",
        password="MySuperSecretPassword",
        cert_verify=False,
    )

    api.protocol_version()
    api.authenticate(action="logout")
    api.authenticate()
    api.list_vms()
