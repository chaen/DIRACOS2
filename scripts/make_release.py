#!/usr/bin/env python
import argparse
import base64
import difflib
from pathlib import Path
from io import BytesIO
import logging
import re
import subprocess
import tempfile
import zipfile

from packaging.version import Version, InvalidVersion
import requests
from uritemplate import expand as uri_expand

CONSTRUCT_VERSION_PATTERN = re.compile(r"version: *(\d+\.\d.+) *\n")
END_HEADER_MAGIC = b"@@END_HEADER@@"
PLATFORM_MAPPING = {
    "linux-64": "Linux-aarch64",
    "linux-aarch64": "Linux-x86_64",
    "linux-ppc64le": "Linux-ppc64le",
}
logging.basicConfig(level=logging.INFO)


def main(
    run_id=None,
    artifacts_dir=None,
    requested_version=None,
    workflow_fn="build-and-test.yml",
    release_notes_fn=None,
    dry_run=True,
):
    """Make a new release of DIRACOS2 based on a GitHub Actions CI run

    Releases are made by:

    1. Download the artifact from a GitHub Actions CI run
    2. Editing it in place to change the version number
    3. Creating a pre-release in GitHub
    4. Uploading release artifacts to the new pre-release
    5. If the version number is not a pre-release: converting the pre-release to a full release
       causing the "latest" release to update
    6. Editing the current "main" branch to be one version higher than the current latest release

    Authentication is performed using the GitHub API token which is automatically made available
    to all GitHub Actions jobs.

    :param str run_id: The GitHub Actions run ID or, if missing, defaults to the most recent
    :param str artifacts_dir: Directory containing artefacts
    :param str requested_version: A version to embed in the DIRACOS2 installer, overriding
        the pre-existing value from when it was built
    :param str workflow_fn: The name of the GitHub Actions workflow configuration file
    :param str release_notes_fn: Path to a file containing release notes
    """
    if run_id is None and not artifacts_dir:
        # Find the run pipeline for the main branch
        r = requests.get(
            f"{api_root}/actions/workflows/{workflow_fn}/runs",
            params={"branch": "main"},
            headers=headers,
        )
        r.raise_for_status()
        run_id = r.json()["workflow_runs"][0]["id"]
        logging.info(f"Run ID was not provided, using: {run_id}")

    # Download the artifacts
    installers = {}
    for platform in ["linux-64", "linux-aarch64", "linux-ppc64le"]:
        logging.info(f"Getting installer for {platform}")
        if artifacts_dir:
            assert dry_run
            installers[platform] = get_installer_artifacts_local(artifacts_dir, platform)
        else:
            installers[platform] = get_installer_artifacts(run_id, platform)

        # Patch the installer to be the requested version
        header, installer_data = installers[platform]["installer"].split(END_HEADER_MAGIC, 1)
        header = header.decode()
        installer_metadata = dict(re.findall(r"# ([A-Z]+): +(.+)", header))
        logging.info(f"Found installer metadata {installer_metadata}")
        this_version, next_version = get_version(requested_version, installer_metadata)
        if dry_run:
            logging.info(f"Mock release {this_version} next version will be {next_version}")
        else:
            logging.info(f"Releasing {this_version} next version will be {next_version}")
        # There should be once instance of the version string in the header and
        # the rest should be "DIRACOS $VER". Check this is the case.
        assert (
            header.count(installer_metadata["VER"])
            == header.count(f"DIRACOS {installer_metadata['VER']}") + 1
        )
        # Update the version in the installer to be the requested one
        header = header.replace(installer_metadata["VER"], this_version)
        installers[platform]["installer"] = header.encode() + END_HEADER_MAGIC + installer_data

    # Load the release notes
    release_notes = make_release_notes(this_version, installers)

    if dry_run:
        print(release_notes)
    else:
        # Create the GitHub release
        make_release(installers, this_version, release_notes)
        # Update the construct.yaml on main
        bump_version_in_main(next_version)


def get_artifacts_zip(artifacts, artifact_name):
    """Download an artifact from a GitHub actions CI run

    :param dict artifacts: Mapping of artifacts names to data from
        https://developer.github.com/v3/actions/artifacts/#list-workflow-run-artifacts
    :param str artifact_name: The key in the dictionary to download
    :returns: An in-memory zipfile.ZipFile object
    """
    r = requests.get(
        artifacts[artifact_name]["archive_download_url"],
        headers={"Authorization": f"token {token}"},
        stream=True,
    )
    r.raise_for_status()
    decoding_classes = {"application/zip": zipfile.ZipFile}
    return decoding_classes[r.headers["Content-Type"]](BytesIO(r.content))


def get_version(version, installer_metadata):
    """Extract the version from the metadata written by conda-constructor

    This function is fragile and based on the implementation of conda-constructor in
    https://github.com/conda/constructor/blob/master/constructor/header.sh

    :param str version: Override the version data contained in the DIRACOS2 installer with this version number
    :param dict installer_metadata: The metadata extracted from the header of the DIRACOS2 installer
    :returns: A tuple of ``str`` containing (current_version, next_version)
    """
    if version is None:
        # If no version is given, convert the build version number to a release version
        version = Version(installer_metadata["VER"])
        version = ".".join(map(str, version.release))
    version = Version(version)

    if version.is_prerelease:
        # Bump the pre-release digit
        next_version = [
            ".".join(map(str, version.release)),
            "".join(map(str, version.pre[:-1] + (version.pre[-1] + 1,))),
        ]
    else:
        # Bump the least significant digit
        next_version = [
            ".".join(map(str, version.release[:-1] + (version.release[-1] + 1,))),
            "a1",
        ]

    return str(version), "".join(next_version)


def get_installer_artifacts(run_id, platform):
    """Download the artifacts from a GitHub Actions run

    :param int run_id: The GitHub Actions run ID to download artifacts from
    :param str platform: The platform to download the installer for
    :raises RuntimeError: The GitHub Actions run was not successful
    :returns: A dictionary containing:
        * ``commit_hash``: Git revision used for the given Run ID
        * ``environment_yaml``: The `str` corresponding to the ``environment.yaml``
          generated by the DIRACOS2 installer
        * ``installer``: The `bytes` corresponding to the DIRACOS2 installer itself
    """
    result = {}

    r = requests.get(f"{api_root}/actions/runs/{run_id}", headers=headers)
    r.raise_for_status()
    run_info = r.json()
    if run_info["conclusion"] != "success":
        raise RuntimeError(
            f"Run {run_id} has not succeeded, its status is {run_info['conclusion']}"
        )
    result["commit_hash"] = run_info["head_sha"]

    r = requests.get(f"{api_root}/actions/runs/{run_id}/artifacts", headers=headers)
    r.raise_for_status()
    artifacts = {x["name"]: x for x in r.json()["artifacts"]}

    if platform == "linux-64":
        result["environment_yaml"] = (
            get_artifacts_zip(artifacts, f"environment-yaml-{platform}")
            .read("environment.yaml")
            .decode()
        )

    installer_zip = get_artifacts_zip(artifacts, f"installer-{platform}")
    if len(installer_zip.filelist) != 1:
        raise NotImplementedError(installer_zip.filelist)
    installer_info = installer_zip.filelist.pop()
    logging.info(f"Found installer: {installer_info.filename}")
    result["installer"] = installer_zip.read(installer_info)

    return result


def get_installer_artifacts_local(artifacts_dir, platform):
    """Download the artifacts from a GitHub Actions run

    :param str artifacts_dir: Directory containing artefacts
    :param str platform: The platform to download the installer for
    :returns: A dictionary containing:
        * ``environment_yaml``: The `str` corresponding to the ``environment.yaml``
          generated by the DIRACOS2 installer
        * ``installer``: The `bytes` corresponding to the DIRACOS2 installer itself
    """
    result = {}
    if platform == "linux-64":
        result["environment_yaml"]= (Path(artifacts_dir) / f"environment-yaml-{platform}" / "environment.yaml").read_text()
    result["installer"] = next((Path(artifacts_dir) / f"installer-{platform}").glob(f"DIRACOS*.sh")).read_bytes()
    return result


def changes_since_last_version(version, environment_yaml, platform):
    """Generate diffs of the packages installed since the previous version

    :param str version: The version of the new release
    :param str environment_yaml: The `str` corresponding to the ``environment.yaml``
        generated by the DIRACOS2 installer
    :param str platform: The platform to compare against
    :returns: A tuple of the:
        * The version number of the previous release
        * A diff of changes to the environment.yaml specification with build strings ignored
        * A diff of changes to the environment.yaml specification
    """
    alt_platform = PLATFORM_MAPPING[platform]

    # Find the previous release
    r = requests.get(f"{api_root}/releases", params={"per_page": 100}, headers=headers)
    r.raise_for_status()
    releases = {}
    for release in r.json():
        for asset in release["assets"]:
            # TODO: This first entry should be removed
            if asset["name"] in ["DIRACOS-environment.yaml", f"DIRACOS-{alt_platform}-environment.yaml"]:
                break
        else:
            raise NotImplementedError(
                f"Failed to find DIRACOS-environment.yaml for {release['tag_name']}"
            )
        try:
            tag_version = Version(release["tag_name"])
        except InvalidVersion:
            logging.info(f"Skipping invalid tag {release['tag_name']}")
        else:
            releases[tag_version] = asset["browser_download_url"]
    version = Version(version)
    sorted_releases = sorted(list(releases) + [version])
    previous_version = sorted_releases[sorted_releases.index(version) - 1]

    # Download the previous release's environment.yaml
    previous_yaml_url = releases[previous_version]
    r = requests.get(previous_yaml_url)
    r.raise_for_status()
    previous_environment_yaml = r.text

    # Generate the full diff
    diff_full = "\n".join(
        difflib.unified_diff(
            previous_environment_yaml.split("\n"),
            environment_yaml.split("\n"),
            n=0,
            lineterm="",
        )
    )

    # Generate the diff ignoring build numbers
    pattern = re.compile(r"(^\s+\- [^=]+=[^=]+)=[^=]+$", re.MULTILINE)
    previous_environment_yaml = pattern.sub(r"\1", previous_environment_yaml)
    environment_yaml = pattern.sub(r"\1", environment_yaml)
    diff_without_builds = "\n".join(
        difflib.unified_diff(
            previous_environment_yaml.split("\n"),
            environment_yaml.split("\n"),
            n=0,
            lineterm="",
        )
    )

    return str(previous_version), diff_without_builds, diff_full


def make_release_notes(version, installers):
    """Generate release notes

    :param str version: The version of the new release
    :param bytes installers: The result of ``get_installer_artifacts``
    """
    r = requests.get(
        "https://raw.githubusercontent.com/DIRACGrid/DIRAC/integration/"
        "docs/diracdoctools/scripts/dirac-docs-get-release-notes.py"
    )
    r.raise_for_status()
    with tempfile.NamedTemporaryFile(delete=False, mode="wt") as tmp:
        tmp.write(r.text)

    release_notes = subprocess.check_output([
        "python",
        tmp.name,
        "--sinceLatestTag",
        "-r=DIRACGrid/DIRACOS2",
        "--branches=main",
        f"--token={token}",
    ], text=True)
    release_notes = "\n".join(release_notes.split("\n")[2:]).strip()

    previous_version, diff_without_builds, diff_full = changes_since_last_version(
        version, installers["linux-64"]["environment_yaml"], "linux-64"
    )
    return "\n".join(
        [
            "## Release notes",
            "",
            release_notes,
            "",
            "## Package list",
            "",
            "<details>",
            "  <summary>Click to expand!</summary>",
            "",
            "```yaml",
            installers["linux-64"]["environment_yaml"],
            "```",
            "</details>",
            "",
            f"## Changes with respect to {previous_version} ignoring build strings",
            "",
            "<details>",
            "  <summary>Click to expand!</summary>",
            "",
            "```diff",
            diff_without_builds,
            "```",
            "</details>",
            "",
            f"## Full changes with respect to {previous_version}",
            "",
            "<details>",
            "  <summary>Click to expand!</summary>",
            "",
            "```diff",
            diff_full,
            "```",
            "</details>",
        ]
    )


def make_release(installers, version, release_notes):
    """Create a new GitHub release using the given data

    This function always makes a pre-release first to ensure the "latest" release never corresponds
    to one without artifacts uploaded. If the new version number is not a pre-release, as
    determined by PEP-440, it is promoted to at full release after the uploads have completed
    successfully.

    :param bytes installers: The result of ``get_installer_artifacts``
    :param str version: The version of the new release
    :param str release_notes: Release notes to include in the release description
    """
    # Create a draft release
    r = requests.post(
        f"{api_root}/releases",
        json={
            "name": f"DIRACOS {version}",
            "tag_name": version,
            "target_commitish": installers["linux-64"]["commit_hash"],
            "body": release_notes,
            "draft": True,
            "prerelease": Version(version).is_prerelease,
        },
        headers=headers,
    )
    r.raise_for_status()
    release_data = r.json()
    logging.info(f"Created draft release at: {release_data['html_url']}")

    for platform, intaller in installers.items():
        alt_platform = PLATFORM_MAPPING[platform]

        # Upload the installer
        r = requests.post(
            uri_expand(
                release_data["upload_url"],
                name=f"DIRACOS-{version}-{alt_platform}.sh",
            ),
            data=intaller["installer"],
            headers={**headers, "Content-Type": "application/x-sh"},
        )
        r.raise_for_status()

        # Upload the installer again with a stable filename
        r = requests.post(
            uri_expand(
                release_data["upload_url"],
                name=f"DIRACOS-{alt_platform}.sh",
            ),
            data=intaller["installer"],
            headers={**headers, "Content-Type": "application/x-sh"},
        )
        r.raise_for_status()

        if platform != "linux-64":
            logging.warning(
                "Skipping upload of environment.yaml, "
                "currently only supported for linux-64"
            )

        # Upload the environment.yaml
        r = requests.post(
            uri_expand(
                release_data["upload_url"],
                name=f"DIRACOS-{version}-{alt_platform}-environment.yaml",
            ),
            data=intaller["environment_yaml"],
            headers={**headers, "Content-Type": "application/x-yaml"},
        )
        r.raise_for_status()

        # Upload the environment.yaml with a stable filename
        r = requests.post(
            uri_expand(
                release_data["upload_url"],
                name=f"DIRACOS-{alt_platform}-environment.yaml",
            ),
            data=intaller["environment_yaml"],
            headers={**headers, "Content-Type": "application/x-yaml"},
        )
        r.raise_for_status()

    # Publish the release
    r = requests.patch(
        release_data["url"],
        json={
            "draft": False,
        },
        headers=headers,
    )
    r.raise_for_status()
    release_data = r.json()
    logging.info(f"Published release at: {release_data['html_url']}")


def bump_version_in_main(new_version):
    """Edit the construct.yaml file on main to correspond to the next DIRACOS2 version

    :param str new_version: The next version number of DIRACOS2
    """
    r = requests.get(f"{api_root}/contents/construct.yaml", headers=headers)
    r.raise_for_status()
    file_info = r.json()
    data = base64.b64decode(file_info["content"]).decode()

    if match := CONSTRUCT_VERSION_PATTERN.search(data):
        if Version(new_version) <= Version(match.groups()[0]):
            logging.info("Skipping construct.yaml version bump as new_version is outdated")
            return
    else:
        raise NotImplementedError("Failed to find the version from construct.yaml")

    new_data, num_subs = CONSTRUCT_VERSION_PATTERN.subn(
        f"version: {new_version}\n", data
    )
    if num_subs != 1:
        raise RuntimeError(num_subs)

    data = {
        "message": f"Bump version to {new_version}",
        "content": base64.b64encode(new_data.encode()).decode(),
        "sha": file_info["sha"],
        "branch": "main",
    }
    r = requests.put(
        file_info["url"],
        json=data,
        headers=headers,
    )
    r.raise_for_status()
    logging.info(
        f"Pushed commit to bump version to {new_version} as {r.json()['commit']['html_url']}"
    )


# Crude unit tests for get_version
assert get_version(None, {"VER": "2.0a1"}) == ("2.0", "2.1a1")
assert get_version(None, {"VER": "2.0"}) == ("2.0", "2.1a1")
assert get_version(None, {"VER": "2.1"}) == ("2.1", "2.2a1")
assert get_version("2.0a1", {"VER": "2.1"}) == ("2.0a1", "2.0a2")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", required=True)
    parser.add_argument("--owner", default="DIRACGrid")
    parser.add_argument("--repo", default="DIRACOS2")

    parser.add_argument("--run-id")
    parser.add_argument("--version")
    parser.add_argument("--artifacts-dir")
    parser.add_argument("--make-release", action="store_true")
    args = parser.parse_args()

    token = args.token
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {token}",
    }
    api_root = f"https://api.github.com/repos/{args.owner}/{args.repo}"

    if args.version and args.version.startswith("v"):
        raise ValueError('For consistency versions must not start with "v"')

    main(
        run_id=int(args.run_id) if args.run_id else None,
        artifacts_dir=args.artifacts_dir,
        requested_version=str(Version(args.version)) if args.version else None,
        dry_run=not args.make_release,
    )
