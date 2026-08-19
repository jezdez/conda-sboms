from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest
from conda.exceptions import CondaValueError
from conda.models.environment import Environment
from conda.models.match_spec import MatchSpec
from conda.models.records import PackageRecord
from conda.plugins.types import EnvironmentFormat
from cyclonedx.schema import SchemaVersion
from cyclonedx.validation.json import JsonStrictValidator

from conda_sbom.cyclonedx import export_cyclonedx_json
from conda_sbom.plugin import conda_environment_exporters


def _package(
    name: str,
    *,
    version: str = "1.0",
    build: str = "h123_0",
    depends: tuple[str, ...] = (),
    sha256: str | None = None,
    md5: str | None = None,
    license_name: str | None = None,
    url: str | None = None,
    channel: str = "https://conda.anaconda.org/conda-forge",
) -> PackageRecord:
    filename = f"{name}-{version}-{build}.conda"
    return PackageRecord(
        name=name,
        version=version,
        build=build,
        build_number=0,
        channel=channel,
        subdir="linux-64",
        fn=filename,
        depends=list(depends),
        sha256=sha256,
        md5=md5,
        license=license_name,
        size=123,
        url=url or f"https://conda.anaconda.org/conda-forge/linux-64/{filename}",
    )


def _document(environment: Environment) -> dict:
    return json.loads(export_cyclonedx_json(environment))


def _component(document: dict, name: str) -> dict:
    return next(
        component for component in document["components"] if component["name"] == name
    )


def _properties(component: dict) -> dict[str, str]:
    return {
        property_["name"]: property_["value"] for property_ in component["properties"]
    }


def _dependencies(document: dict) -> dict[str, list[str]]:
    return {
        dependency["ref"]: dependency["dependsOn"]
        for dependency in document["dependencies"]
    }


def test_export_maps_resolved_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    openssl = _package("openssl", sha256="c" * 64)
    python = _package(
        "python",
        version="3.13.7",
        depends=("openssl >=3", "__linux >=6"),
        sha256="A" * 64,
        md5="b" * 32,
        license_name="PSF license and custom terms",
        url=(
            "https://user:password@conda.anaconda.org/t/secret/conda-forge/"
            "linux-64/python-3.13.7-h123_0.conda?token=also-secret"
        ),
    )
    virtual = PackageRecord(
        name="__linux",
        version="6.0",
        build="0",
        build_number=0,
        channel="@",
        subdir="linux-64",
        depends=[],
    )
    environment = Environment(
        name="demo",
        platform="linux-64",
        explicit_packages=[python, openssl],
        requested_packages=[MatchSpec("python")],
        external_packages={"pip": ["example==1"]},
        virtual_packages=[virtual],
    )

    output = export_cyclonedx_json(environment)
    document = json.loads(output)

    assert output.endswith("\n")
    assert document["bomFormat"] == "CycloneDX"
    assert document["specVersion"] == "1.7"
    assert document["version"] == 1
    assert "serialNumber" not in document
    assert document["metadata"]["timestamp"] == "1970-01-01T00:00:00+00:00"
    assert document["metadata"]["tools"]["components"][0]["name"] == "conda-sbom"

    python_component = _component(document, "python")
    assert python_component["purl"] == (
        "pkg:conda/python@3.13.7?build=h123_0&channel=conda-forge"
        "&subdir=linux-64&type=conda"
    )
    assert python_component["hashes"] == [
        {"alg": "MD5", "content": "b" * 32},
        {"alg": "SHA-256", "content": "a" * 64},
    ]
    assert python_component["licenses"] == [
        {"license": {"name": "PSF license and custom terms"}}
    ]
    assert python_component["externalReferences"] == [
        {
            "type": "distribution",
            "url": (
                "https://conda.anaconda.org/conda-forge/linux-64/"
                "python-3.13.7-h123_0.conda"
            ),
        }
    ]
    assert _properties(python_component)["conda:package:filename"] == (
        "python-3.13.7-h123_0.conda"
    )

    root = document["metadata"]["component"]
    root_properties = _properties(root)
    assert root_properties["conda:environment:root-dependency-source"] == (
        "requested-packages"
    )
    assert root_properties["conda:environment:external-packages-omitted"] == "1"
    assert root_properties["conda:environment:virtual-packages-omitted"] == "1"
    assert root_properties["conda:environment:dependency-edges-omitted"] == "1"

    dependencies = _dependencies(document)
    assert dependencies[root["bom-ref"]] == [python_component["bom-ref"]]
    assert dependencies[python_component["bom-ref"]] == [
        _component(document, "openssl")["bom-ref"]
    ]
    assert dependencies[_component(document, "openssl")["bom-ref"]] == []
    assert document["compositions"] == [
        {
            "aggregate": "incomplete",
            "assemblies": [root["bom-ref"]],
        },
        {
            "aggregate": "incomplete",
            "dependencies": [python_component["bom-ref"]],
        },
    ]
    assert JsonStrictValidator(SchemaVersion.V1_7).validate_str(output) is None


def test_inferred_roots_cover_a_disconnected_cycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    environment = Environment(
        platform="linux-64",
        explicit_packages=[
            _package("root", depends=("leaf",)),
            _package("leaf"),
            _package("cycle-a", depends=("cycle-b",)),
            _package("cycle-b", depends=("cycle-a",)),
        ],
    )

    document = _document(environment)
    root = document["metadata"]["component"]
    dependencies = _dependencies(document)

    assert dependencies[root["bom-ref"]] == [
        _component(document, "cycle-a")["bom-ref"],
        _component(document, "root")["bom-ref"],
    ]
    assert _properties(root)["conda:environment:root-dependency-source"] == (
        "inferred-graph-roots"
    )
    assert document["compositions"] == [
        {
            "aggregate": "unknown",
            "assemblies": [root["bom-ref"]],
            "dependencies": [root["bom-ref"]],
        }
    ]


def test_export_is_deterministic_for_reordered_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1720000000")
    first = _package("first", depends=("second",))
    second = _package("second")

    forward = Environment(
        platform="linux-64",
        explicit_packages=[first, second],
    )
    reverse = Environment(
        platform="linux-64",
        explicit_packages=[second, first],
    )

    assert export_cyclonedx_json(forward) == export_cyclonedx_json(reverse)


def test_local_channel_paths_are_not_serialized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    private_path = "/Users/alice/private-channel"
    environment = Environment(
        platform="linux-64",
        explicit_packages=[
            _package(
                "private",
                channel=f"file://{private_path}",
                url=f"file://{private_path}/linux-64/private-1.0-h123_0.conda",
            )
        ],
    )

    output = export_cyclonedx_json(environment)
    component = _component(json.loads(output), "private")

    assert private_path not in output
    assert "channel=" not in component["purl"]
    assert "externalReferences" not in component


@pytest.mark.parametrize("epoch", ["tomorrow", "-1"])
def test_invalid_source_date_epoch_fails(
    monkeypatch: pytest.MonkeyPatch,
    epoch: str,
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", epoch)
    environment = Environment(
        platform="linux-64",
        explicit_packages=[_package("example")],
    )

    with pytest.raises(CondaValueError, match="SOURCE_DATE_EPOCH"):
        export_cyclonedx_json(environment)


def test_invalid_hash_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    environment = Environment(
        platform="linux-64",
        explicit_packages=[_package("example", sha256="not-a-sha256")],
    )

    with pytest.raises(CondaValueError, match="Invalid SHA-256 hash"):
        export_cyclonedx_json(environment)


def test_export_requires_exact_records() -> None:
    environment = Environment(
        platform="linux-64",
        requested_packages=[MatchSpec("python")],
    )

    with pytest.raises(CondaValueError, match="requires exact package records"):
        export_cyclonedx_json(environment)


def test_plugin_registration() -> None:
    exporters = list(conda_environment_exporters())

    assert len(exporters) == 1
    assert exporters[0].name == "cyclonedx-json"
    assert exporters[0].aliases == ("cyclonedx", "cdx-json")
    assert exporters[0].environment_format is EnvironmentFormat.environment


def test_conda_discovers_and_runs_exporter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    environment = os.environ.copy()
    environment["CONDA_NO_PLUGINS"] = "false"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "conda",
            "export",
            "--prefix",
            sys.prefix,
            "--format",
            "cyclonedx-json",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    document = json.loads(completed.stdout)

    assert document["specVersion"] == "1.7"
    assert (
        JsonStrictValidator(SchemaVersion.V1_7).validate_str(completed.stdout) is None
    )
