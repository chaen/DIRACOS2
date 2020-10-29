# DIRACOS2

Experimental repository using [conda constructor](https://github.com/conda/constructor) to build a Python 3 DIRACOS installer.

## Installing DIRACOS

These instructions will install the latest release of DIRACOS in a folder named `diracos`. To install a specific version replace `/latest/` in the URL with a version like `/2.0a2/`.

```bash
curl -LO https://github.com/DIRACGrid/DIRACOS2/releases/latest/download/DIRACOS-Linux-x86_64.sh
bash DIRACOS-Linux-x86_64.sh -b -p "$PWD/diracos/"
```

## Building the installer

The DIRACOS installer is a self-extracting shell script that is generated using [conda constructor](https://github.com/conda/constructor). This can be installed using any `conda` installation. If you don't have a local conda installation, you can use the following steps on Linux:

```bash
wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
bash Miniforge3-Linux-x86_64.sh -b -p $PWD/miniforge
# This line is needed every time you wish to use miniforge in a new shell
eval "$($PWD/miniforge/bin/conda shell.bash hook)"
conda install constructor
```

Once you have `constructor` installed, a new installer can be generating from the `construct.yaml` using:

```bash
constructor . --platform=linux-64
```

The packages included are defined in the `construct.yaml` file, see the [upstream documentation](https://github.com/conda/constructor/blob/master/CONSTRUCT.md) for more details.

## Testing the installer

Basic tests of the installer can be ran using an arbitrary docker image by running:

```bash
scripts/run_basic_tests.sh DOCKER_IMAGE DIRACOS_INSTALLER_FILENAME
```

## Extensions

TODO

## Building customised packages

See [`management/conda-recipes`](https://github.com/DIRACGrid/management/tree/master/conda-recipes).

## Making a release

To ensure reproducibility, releases are made from build artifacts from previous pipelines and are tagged using GitHub actions by triggering the [Create release](https://github.com/DIRACGrid/DIRACOS2/actions?query=workflow%3A%22Create+release%22) workflow. This workflow has the following optional parameters:

* **Run ID**: The GitHub Actions workflow run ID. If not given, defaults to the most recent build of the `main` branch.
* **Version number**: A [PEP-440](https://www.python.org/dev/peps/pep-0440/) compliant version number. If not given, defaults to the contents the contents of version field in the `construct.yaml` rounded to the next full release (i.e. `2.4a5` becomes `2.4` and `2.1` remains unchanged). If a pre-release is explicitly give, it will be marked as a pre-release in GitHub and won't affect the `latest` alias.

If the release process fails, a draft release might be left in GitHub. After the issue has been fixed this can be safely deleted before rerunning the CI.

After the release is made a commit will be pushed to master to bump the DIRACOS release number in `construct.yaml` to the next alpha release. If the next alpha release is older than the current contents of `construct.yaml`, this step is skipped.

## Troubleshooting

This section contains a list of know issues that can occur.

### Duplicate files

This error is of the form:

```
File 'include/event.h' found in multiple packages: libevent-2.1.10-hcdb4288_2.tar.bz2, libev-4.33-h516909a_0.tar.bz2
```

When this happens, the offending packages should be fixed upstream in conda-forge. As a temporary workaround, the `ignore_duplicate_files` key in `construct.yaml` can be changed to `true`.
