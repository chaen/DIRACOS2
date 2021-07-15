#!/usr/bin/env bash

# Create the diracosrc
{
    echo "export DIRACOS=$PREFIX"
    echo ''
    echo '# Initialise the conda environment in a way which ignores other conda installations'
    echo 'unset CONDA_SHLVL'
    echo 'eval "$(${DIRACOS}/bin/conda shell.bash hook)"'
    echo 'conda activate "$DIRACOS"'
    echo ''
    echo '# Silence python warnings'
    echo 'export PYTHONWARNINGS=ignore'
    echo ''
    echo '# Davix options (will be default in the future)'
    echo 'export DAVIX_USE_LIBCURL=1'
    echo ''
    echo '# Set up the X509 variables'
    echo ''
    echo '# Function check if folder exist and contins files'
    echo 'function checkDir () {'
    echo '  if [ -z "${1}" ]; then'
    echo '    return 1'
    echo '  fi'
    echo '  if [ -n "$(ls -A "${1}" 2>/dev/null)" ]; then'
    echo '    return 0'
    echo '  fi'
    echo '  return 1'
    echo '}'
    echo ''
    echo '# Add sanity check for X509_CERT_DIR variable'
    echo 'if ! checkDir "$X509_CERT_DIR" ; then'
    echo '  export X509_CERT_DIR="/etc/grid-security/certificates"'
    echo '  if ! checkDir "$X509_CERT_DIR" ; then'
    echo "    export X509_CERT_DIR='${PREFIX}/etc/grid-security/certificates'"
    echo '  fi'
    echo 'fi'
    echo ''
    echo '# Add sanity check for X509_VOMS_DIR variable'
    echo 'if ! checkDir "$X509_VOMS_DIR" ; then'
    echo '  export X509_VOMS_DIR="/etc/grid-security/vomsdir"'
    echo '  if ! checkDir "$X509_VOMS_DIR" ; then'
    echo "    export X509_VOMS_DIR='${PREFIX}/etc/grid-security/vomsdir'"
    echo '  fi'
    echo 'fi'
    echo ''
    echo '# Add sanity check for X509_VOMSES variable'
    echo 'if ! checkDir "$X509_VOMSES" ; then'
    echo '  export X509_VOMSES="/etc/vomses"'
    echo '  if ! checkDir "$X509_VOMSES" ; then'
    echo "    export X509_VOMSES='${PREFIX}/etc/grid-security/vomses'"
    echo '  fi'
    echo 'fi'
    echo ''
} > "$PREFIX/diracosrc"

# Workaround for the incorrect etc directory in v7r2
ln -s "$PREFIX/etc" "$PREFIX/lib/python3.9/site-packages/etc"

# Print further install instructions
echo ""
echo "DIRACOS has been installed sucessfully in $PREFIX"
echo ""
echo " * It can now be activated with:"
echo "       source $PREFIX/diracosrc"
echo ""
echo " * To install vanilla DIRAC then run:"
echo "       pip install DIRAC"
echo ""
echo "   Alternatively, to install a specific version:"
echo "       pip install DIRAC==7.2.0a34"
echo ""
echo "   Alternatively, to install a DIRAC extension, install the associated Python package. E.g. for LHCbDIRAC run:"
echo "       pip install LHCbDIRAC"
echo ""
echo " * You can then get the configuration for your DIRAC installation using (chnaging MY_SETUP and MY_CONFIGURATION_URL as appropriate):"
echo "       dirac-proxy-init --nocs"
echo "       dirac-configure -S MY_SETUP -C MY_CONFIGURATION_URL --SkipCAChecks"
echo "       dirac-proxy-init"
echo ""
echo "For more advanced installation instructions see:"
echo "https://dirac.readthedocs.io/en/integration/DeveloperGuide/DevelopmentEnvironment/DeveloperInstallation/editingCode.html#creating-a-development-environment-with-diracos2"
echo ""
