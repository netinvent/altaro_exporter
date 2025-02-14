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
__build__ = "2024091001"


import sys
from logging import getLogger
import secrets
from argparse import ArgumentParser
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.responses import Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi_offline import FastAPIOffline
from altaro_exporter.__version__ import __version__
from altaro_exporter.configuration import load_config
from altaro_exporter.altaro_api import AltaroAPI
import prometheus_client


logger = getLogger()


# Make sure we load given config files again
default_config_file = "altaro_exporter.yaml"
parser = ArgumentParser()
parser.add_argument(
    "-c",
    "--config-file",
    dest="config_file",
    type=str,
    default=default_config_file,
    required=False,
    help="Path to altaro_exporter.yaml file",
)
args = parser.parse_args()
if args.config_file:
    config_dict = load_config(args.config_file)
else:
    logger.critical("No configuration file given. Exiting.")
    sys.exit(1)

if not config_dict:
    logger.critical("No configuration file loaded. Exiting.")
    sys.exit(1)

altaro_rest_host = config_dict.g("altaro_server.rest_host")
altaro_rest_port = config_dict.g("altaro_server.rest_port")
altaro_rest_path = config_dict.g("altaro_server.rest_path")
altaro_server_address = config_dict.g("altaro_server.server_address")
altaro_server_port = config_dict.g("altaro_server.server_port")
username = config_dict.g("altaro_server.username")
password = config_dict.g("altaro_server.password")
domain = config_dict.g("altaro_server.domain")

try:
    include_unconfigured = config_dict["options"]["include_unconfigured"]
except:
    include_unconfigured = True
try:
    include_non_scheduled = config_dict["options"]["include_non_scheduled"]
except:
    include_non_scheduled = True


app = FastAPIOffline()
metrics_app = prometheus_client.make_asgi_app()
app.mount("/metrics", metrics_app)
security = HTTPBasic()

api = AltaroAPI(
    altaro_rest_host=altaro_rest_host,
    altaro_rest_port=altaro_rest_port,
    altaro_rest_path=altaro_rest_path,
    altaro_server_address=altaro_server_address,
    altaro_server_port=altaro_server_port,
    username=username,
    password=password,
    domain=domain,
    cert_verify=False,
)
api.authenticate()


def anonymous_auth():
    return "anonymous"


def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    current_username_bytes = credentials.username.encode("utf8")
    correct_username_bytes = config_dict["http_server"]["username"].encode("utf-8")
    is_correct_username = secrets.compare_digest(
        current_username_bytes, correct_username_bytes
    )
    current_password_bytes = credentials.password.encode("utf8")
    correct_password_bytes = config_dict["http_server"]["password"].encode("utf-8")
    is_correct_password = secrets.compare_digest(
        current_password_bytes, correct_password_bytes
    )
    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


try:
    if config_dict["http_server"]["no_auth"] is True:
        logger.warning("Running without HTTP authentication")
        auth_scheme = anonymous_auth
    else:
        logger.info("Running with HTTP authentication")
        auth_scheme = get_current_username
except (KeyError, AttributeError, TypeError):
    auth_scheme = get_current_username
    logger.info("Running with HTTP authentication")


@app.get("/")
async def api_root(auth=Depends(auth_scheme)):
    return {"app": __appname__, "version": __version__}


@app.get("/metrics")
async def get_metrics(auth=Depends(auth_scheme)):
    try:
        api.list_vms(
            include_unconfigured=include_unconfigured,
            include_non_scheduled=include_non_scheduled,
        )
        api.reset_vm_metrics()
        content = prometheus_client.generate_latest()

    except KeyError:
        logger.critical("Bogus configuration file. Missing Altaro_hosts key.")
    return Response(
        content=content, media_type="text/plain"
    )
