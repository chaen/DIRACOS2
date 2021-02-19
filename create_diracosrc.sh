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
    echo ''
    echo '# Davix options (will be default in the future)'
    echo 'export DAVIX_USE_LIBCURL=1'
} > "$PREFIX/diracosrc"

# Print further install instructions
echo ""
echo "DIRACOS has been installed sucessfully in $PREFIX"
echo ""
echo "* It can now be activated with:"
echo "    source $PREFIX/diracosrc"
echo ""
echo " * To install vanilla DIRAC then run:"
echo "    pip install DIRAC"
echo ""
echo "Alternatively, to install a specific version:"
echo "    pip install DIRAC==7.2.0a34"
echo ""
echo "Alternatively, to install a DIRAC extension, install the associated Python package. E.g. for LHCbDIRAC run:"
echo "    pip install LHCbDIRAC"
echo ""
echo " * You can then get the configuration for your DIRAC installation using (chnaging MY_SETUP and MY_CONFIGURATION_URL as appropriate):"
echo "    dirac-proxy-init --nocs"
echo "    dirac-configure -S MY_SETUP -C MY_CONFIGURATION_URL --SkipCAChecks"
echo "    dirac-proxy-init"
echo ""
echo "For more advanced installation instructions see:"
echo "https://todo"
