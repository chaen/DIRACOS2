#!/usr/bin/env bash

# Create the diracosrc
{
    echo "export DIRACOS=$PREFIX"
    echo ''
    echo '# Initialise the conda environment'
    echo 'eval "$(${DIRACOS}/bin/conda shell.bash hook)"'
    echo ''
    echo '# Silence python warnings'
    echo 'export PYTHONWARNINGS=ignore'
} > "$PREFIX/diracosrc"
