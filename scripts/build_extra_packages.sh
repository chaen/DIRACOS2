#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

COLOR_OFF='\033[0m'
RED='\033[0;31m'
GREEN='\033[0;32m'

SCRIPTPATH="$( cd "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"
DIRACOS_REPO_PATH="$(dirname "${SCRIPTPATH}")"
EXTRA_PACKAGES_DIR="${DIRACOS_REPO_PATH}/extra-packages"
export CONDA_BLD_PATH="${DIRACOS_REPO_PATH}/conda-bld"

NUM_FAILURES=0
for RECIPE_DIR in "${EXTRA_PACKAGES_DIR}"/*/; do
    PACKAGE_NAME="$(basename "${RECIPE_DIR}")"
    echo -e "${GREEN}Building ${PACKAGE_NAME}${COLOR_OFF}"
    # TODO: This should run in docker
    if conda build -m "${EXTRA_PACKAGES_DIR}/conda_build_config.yaml" "${RECIPE_DIR}"; then
        echo -e "${GREEN}Sucessfully built ${PACKAGE_NAME}${COLOR_OFF}"
    else
        echo -e "${RED}ERROR: Failed to build ${PACKAGE_NAME}${COLOR_OFF}"
        let "NUM_FAILURES=NUM_FAILURES+1"
    fi
done

echo -e "Summary: ${NUM_FAILURES} packages failed to build"
exit ${NUM_FAILURES}
