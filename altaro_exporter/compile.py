#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of altaro_exporter

__intname__ = "altaro_exporter.compile"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023-2024 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2024082701"
__version__ = "1.0.0"


"""
Nuitka compilation script tested for
 - windows 32 bits (Vista+)
 - windows 64 bits
 - Linux i386
 - Linux i686-
 - Linux armv71
"""


import sys
import os

# Insert parent dir as path se we get to use altaro_exporter as package
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

print(os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))


import shutil
import argparse
import atexit
from command_runner import command_runner
from ofunctions.platform import python_arch, get_os
from altaro_exporter.path_helper import CURRENT_DIR
import nuitka


from resources.customization import (
    COMPANY_NAME,
    TRADEMARKS,
    PRODUCT_NAME,
    FILE_DESCRIPTION,
    COPYRIGHT,
)

import glob

del sys.path[0]


def _read_file(filename):
    here = os.path.abspath(os.path.dirname(__file__))
    if sys.version_info[0] < 3:
        # With python 2.7, open has no encoding parameter, resulting in TypeError
        # Fix with io.open (slow but works)
        from io import open as io_open

        try:
            with io_open(
                os.path.join(here, filename), "r", encoding="utf-8"
            ) as file_handle:
                return file_handle.read()
        except IOError:
            # Ugly fix for missing requirements.txt file when installing via pip under Python 2
            return ""
    else:
        with open(os.path.join(here, filename), "r", encoding="utf-8") as file_handle:
            return file_handle.read()


def get_metadata(package_file):
    """
    Read metadata from package file
    """

    _metadata = {}

    for line in _read_file(package_file).splitlines():
        if line.startswith("__version__") or line.startswith("__description__"):
            delim = "="
            _metadata[line.split(delim)[0].strip().strip("__")] = (
                line.split(delim)[1].strip().strip("'\"")
            )
    return _metadata


def have_nuitka_commercial():
    try:
        import nuitka.plugins.commercial

        print("Running with nuitka commercial")
        return True
    except ImportError:
        print("Running with nuitka open source")
        return False


def compile(arch: str):
    source_program = "altaro_exporter.py"

    if os.name == "nt":
        program_executable = "altaro_exporter-{}.exe".format(arch)
        platform = "windows"
    elif sys.platform.lower() == "darwin":
        platform = "darwin"
        program_executable = "altaro_exporter-{}".format(arch)
    else:
        platform = "linux"
        program_executable = "altaro_exporter-{}".format(arch)

    PACKAGE_DIR = "altaro_exporter"

    BUILDS_DIR = os.path.abspath(os.path.join(CURRENT_DIR, os.pardir, "BUILDS"))
    OUTPUT_DIR = os.path.join(BUILDS_DIR, platform, arch)

    if not os.path.isdir(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    PYTHON_EXECUTABLE = sys.executable

    # altaro_exporter compilation
    # Strip possible version suffixes '-dev'
    _altaro_exporter_version = altaro_exporter_version.split("-")[0]
    PRODUCT_VERSION = _altaro_exporter_version + ".0"
    FILE_VERSION = _altaro_exporter_version + ".0"

    file_description = "{} P{}-{}".format(
        FILE_DESCRIPTION,
        sys.version_info[1],
        arch,
    )

    icon_file = os.path.join(CURRENT_DIR, os.pardir, "resources", "netinvent.ico")

    # NUITKA_OPTIONS = " --clang"
    # As of Nuitka v1.8, `-c` parameter is used to prevent fork bomb self execution
    # We don't need this, so let's disable it so we can use `-c`as `--config-file` shortcut
    NUITKA_OPTIONS = " --no-deployment-flag=self-execution"
    NUITKA_OPTIONS += " --enable-plugin=data-hiding" if have_nuitka_commercial() else ""

    # Nuitka needs explicit imports for fastapi etc
    NUITKA_OPTIONS += " --include-module=pydantic.type_adapter --include-module=gunicorn.glogging --include-module=urllib3 --include-module=uvicorn --include-module=uvicorn.workers"

    # Nuitka also needs static fastapi files
    if os.name == "nt":
        python_dir = ""
    else:
        python_dir = f"/python{sys.version_info[0]}.{sys.version_info[1]}"
    NUITKA_OPTIONS += " --include-data-dir=venv/lib{}/site-packages/fastapi_offline/static=fastapi_offline/static".format(
        python_dir
    )

    NUITKA_OPTIONS += " --standalone"

    if os.name == "nt" and have_nuitka_commercial():
        NUITKA_OPTIONS += (
            " --enable-plugin=windows-service --windows-service-name=Altaro_Exporter"
        )
        print("Building a windows service executable")
    else:
        print(
            "You need Nuitka commercial to build a windows service. We'll build a plain exe. Consider buying Nuitka commercial for more features."
        )

    EXE_OPTIONS = '--company-name="{}" --product-name="{}" --file-version="{}" --product-version="{}" --copyright="{}" --file-description="{}" --trademarks="{}"'.format(
        COMPANY_NAME,
        PRODUCT_NAME,
        FILE_VERSION,
        PRODUCT_VERSION,
        COPYRIGHT,
        file_description,
        TRADEMARKS,
    )

    CMD = '{} -m nuitka --python-flag=no_docstrings --python-flag=-O {} {} --windows-icon-from-ico="{}" --output-dir="{}" --output-filename="{}" {}'.format(
        PYTHON_EXECUTABLE,
        NUITKA_OPTIONS,
        EXE_OPTIONS,
        icon_file,
        OUTPUT_DIR,
        program_executable,
        source_program,
    )

    print(CMD)
    errors = False
    exit_code, output = command_runner(CMD, timeout=0, live_output=True)
    if exit_code != 0:
        errors = True

    print(f"COMPILED {'WITH SUCCESS' if not errors else 'WITH ERRORS'}")
    if not create_archive(
        platform=platform,
        output_dir=OUTPUT_DIR,
    ):
        errors = True
    return not errors


def create_archive(platform: str, output_dir: str):
    """
    Create tar releases for each compiled version
    """
    nuitka_standalone_suffix = ".dist"
    compiled_output = os.path.join(
        output_dir, "altaro_exporter{}".format(nuitka_standalone_suffix)
    )
    new_compiled_output = compiled_output[: -len(nuitka_standalone_suffix)]
    if os.path.isdir(new_compiled_output):
        shutil.rmtree(new_compiled_output)
    shutil.move(compiled_output, new_compiled_output)
    if os.name == "nt":
        archive_extension = "zip"
    else:
        archive_extension = "tar.gz"
    target_archive = f"{output_dir}/altaro_exporter-{platform}.{archive_extension}"
    if os.path.isfile(target_archive):
        os.remove(target_archive)
    if os.name == "nt":
        # This supposes Windows 10 that comes with tar
        # This tar version will create a plain zip file when used with -a (and without -z which creates gzip files)
        cmd = f"tar -a -c -f {target_archive} -C {output_dir} {os.path.basename(new_compiled_output)}"
    else:
        cmd = f"tar -czf {target_archive} -C {output_dir} ./{os.path.basename(new_compiled_output)}"
    print(f"Creating archive {target_archive}")
    exit_code, output = command_runner(cmd, timeout=0, live_output=True, shell=True)
    shutil.move(new_compiled_output, compiled_output)
    if exit_code != 0:
        print(f"ERROR: Cannot create archive file for {platform}:")
        print(output)
        return False
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="altaro_exporter compile.py",
        description="Compiler script for altaro_exporter",
    )
    args = parser.parse_args()

    try:
        errors = False

        altaro_exporter_version = get_metadata(
            os.path.join(CURRENT_DIR, "__version__.py")
        )["version"]

        result = compile(
            arch=python_arch(),
        )
        if result:
            print("SUCCESS: MADE build")
        else:
            print("ERROR: Failed making")
            errors = True
        if errors:
            print("ERRORS IN BUILD PROCESS")
        else:
            print("SUCCESS BUILDING")
    except Exception:
        print("COMPILATION FAILED")
        raise
