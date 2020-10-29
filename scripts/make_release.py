#!/usr/bin/env python
import argparse
import base64
from io import BytesIO
import os
import re
import zipfile

from packaging.version import Version
import requests
from uritemplate import expand as uri_expand


CONSTRUCT_VERSION_PATTERN = re.compile(r"version: *(\d+\.\d.+) *\n")
END_HEADER_MAGIC = b"@@END_HEADER@@"


def get_artifacts_zip(artifacts, artifact_name):
    r = requests.get(
        artifacts[artifact_name]["archive_download_url"],
        headers={"Authorization": f"token {token}"},
        stream=True
    )
    r.raise_for_status()
    decoding_classes = {
        "application/zip": zipfile.ZipFile
    }
    return decoding_classes[r.headers['Content-Type']](BytesIO(r.content))


def get_version(version, installer_metadata):
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
            "a1"
        ]

    return str(version), "".join(next_version)


def main(run_id=None, requested_version=None, workflow_fn="build-and-test.yml"):
    if run_id is None:
        # Find the run pipeline for the main branch
        r = requests.get(
            f"{api_root}/actions/workflows/{workflow_fn}/runs",
            params={"branch": "main"},
            headers=headers,
        )
        r.raise_for_status()
        run_id = r.json()["workflow_runs"][0]["id"]
        print("Run ID was not provided, using:", run_id)

    # Download the artifacts
    commit_hash, environment_yaml, installer = get_installer_artifacts(run_id)

    # Patch the installer to be the requested version
    header, installer_data = installer.split(END_HEADER_MAGIC, 1)
    header = header.decode()
    installer_metadata = dict(re.findall(r"# ([A-Z]+): +(.+)", header))
    print("Found installer metadata", installer_metadata)
    if int(installer_metadata["LINES"]) - 1 != len(header.split("\n")):
        raise NotImplementedError(len(header.split("\n")))
    this_version, next_version = get_version(requested_version, installer_metadata)
    print(f"Releasing {this_version} next version will be {next_version}")
    # There should be once instance of the version string in the header and
    # the rest should be "DIRACOS $VER". Check this is the case.
    assert header.count(installer_metadata["VER"]) == header.count(f"DIRACOS {installer_metadata['VER']}") + 1
    # Update the version in the installer to be the requested one
    header = header.replace(installer_metadata["VER"], this_version)
    installer = header.encode() + END_HEADER_MAGIC + installer_data

    # Create the GitHub release
    make_release(installer, environment_yaml, this_version, commit_hash)

    # Update the construct.yaml on main
    bump_version_in_main(next_version)


def get_installer_artifacts(run_id):
    r = requests.get(f"{api_root}/actions/runs/{run_id}", headers=headers)
    r.raise_for_status()
    run_info = r.json()
    if run_info["conclusion"] != "success":
        raise RuntimeError(f"Run {run_id} has not succeeded, its status is {run_info['conclusion']}")

    r = requests.get(f"{api_root}/actions/runs/{run_id}/artifacts", headers=headers)
    r.raise_for_status()
    artifacts = {x["name"]: x for x in r.json()["artifacts"]}

    environment_yaml = get_artifacts_zip(artifacts, "environment-yaml").read("environment.yaml").decode()

    installer_zip = get_artifacts_zip(artifacts, "installer")
    if len(installer_zip.filelist) != 1:
        raise NotImplementedError(installer_zip.filelist)
    installer_info = installer_zip.filelist.pop()
    print("Found installer:", installer_info.filename)
    installer = installer_zip.read(installer_info)

    return run_info["head_sha"], environment_yaml, installer


def make_release(installer, environment_yaml, version, commit_hash):
    release_notes = "\n".join([
        f"# DIRACOS {version}",
        "",
        "## Changes",
        "* TODO",
        "",
        "## Package list",
        "```yaml",
        environment_yaml,
        "```",
    ])

    # Create a draft release
    r = requests.post(
        f"{api_root}/releases",
        json={
        "tag_name": version,
        "target_commitish": commit_hash,
        "body": release_notes,
        "draft": True,
        "prerelease": Version(version).is_prerelease,
        },
        headers=headers,
    )
    r.raise_for_status()
    release_data = r.json()
    print(f"Created draft release at: {release_data['html_url']}")

    # Upload the installer
    r = requests.post(
        uri_expand(
            release_data["upload_url"],
            name=f"DIRACOS-{version}-Linux-x86_64.sh",
        ),
        data=installer,
        headers={**headers, "Content-Type": "application/x-sh"},
    )
    r.raise_for_status()

    # Upload the installer again with a stable filename
    r = requests.post(
        uri_expand(
            release_data["upload_url"],
            name=f"DIRACOS-Linux-x86_64.sh",
        ),
        data=installer,
        headers={**headers, "Content-Type": "application/x-sh"},
    )
    r.raise_for_status()

    # Upload the environment.yaml
    r = requests.post(
        uri_expand(
            release_data["upload_url"],
            name=f"DIRACOS-{version}-environment.yaml",
        ),
        data=environment_yaml,
        headers={**headers, "Content-Type": "application/x-yaml"},
    )
    r.raise_for_status()

    # Upload the environment.yaml with a stable filename
    r = requests.post(
        uri_expand(
            release_data["upload_url"],
            name=f"DIRACOS-environment.yaml",
        ),
        data=environment_yaml,
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
    print(f"Published release at: {release_data['html_url']}")


def bump_version_in_main(new_version):
    r = requests.get(f"{api_root}/contents/construct.yaml", headers=headers)
    r.raise_for_status()
    file_info = r.json()
    data = base64.b64decode(file_info["content"]).decode()

    if match := CONSTRUCT_VERSION_PATTERN.search(data):
        if Version(new_version) <= Version(match.groups()[0]):
            print("Skipping construct.yaml version bump as new_version is outdated")
            return
    else:
        raise NotImplementedError("Failed to find the version from construct.yaml")

    new_data, num_subs = CONSTRUCT_VERSION_PATTERN.subn(f"version: {new_version}\n", data)
    if num_subs != 1:
        raise RuntimeError(num_subs)

    r = requests.put(
        file_info["url"],
        json={
            "message": f"Bump version to {new_version}",
            "content": base64.b64encode(new_data.encode()).decode(),
            "sha": file_info["sha"],
        },
        headers=headers,
    )
    r.raise_for_status()
    print(f"Pushed commit to bump version to {new_version} as {r.json()['commit']['html_url']}")


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
        requested_version=str(Version(args.version)) if args.version else None
    )
