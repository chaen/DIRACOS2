#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

IMAGE_NAME=$1
DIRACOS_INSTALLER=$2

exec docker run --rm --privileged -v "${PWD}":/diracos-repo "${IMAGE_NAME}" bash -c "bash /diracos-repo/${DIRACOS_INSTALLER} -b -p diracos && source diracos/diracosrc && pytest -v /diracos-repo/tests/test_import.py && bash /diracos-repo/tests/test_cli.sh"
