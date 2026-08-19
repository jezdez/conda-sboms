from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from string import hexdigits
from typing import TYPE_CHECKING
from urllib.parse import quote, urlsplit, urlunsplit
from uuid import UUID

from conda.common.url import remove_auth, split_anaconda_token
from conda.exceptions import CondaValueError
from conda.models.match_spec import MatchSpec
from cyclonedx.model import (
    ExternalReference,
    ExternalReferenceType,
    HashAlgorithm,
    HashType,
    Property,
    XsUri,
)
from cyclonedx.model.bom import Bom, BomMetaData
from cyclonedx.model.component import Component, ComponentType
from cyclonedx.model.dependency import Dependency
from cyclonedx.model.license import DisjunctiveLicense
from cyclonedx.model.tool import ToolRepository
from cyclonedx.output.json import JsonV1Dot7
from packageurl import PackageURL

from . import __version__

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from typing import Final

    from conda.models.environment import Environment
    from conda.models.records import PackageRecord
    from cyclonedx.model.bom_ref import BomRef

_PLACEHOLDER_UUID = UUID("00000000-0000-4000-8000-000000000000")

FORMAT: Final = "cyclonedx-json"
ALIASES: Final = ("cyclonedx", "cdx-json")
DEFAULT_FILENAMES: Final = ("*.cdx.json",)
DESCRIPTION: Final = "CycloneDX 1.7 JSON software bill of materials"


def export_cyclonedx_json(environment: Environment) -> str:
    """Export a resolved conda environment as CycloneDX 1.7 JSON."""
    if not environment.explicit_packages:
        raise CondaValueError(
            "CycloneDX export requires exact package records. Export an installed "
            "environment or a resolved lockfile."
        )

    records = sorted(
        environment.explicit_packages,
        key=lambda record: (
            _normalized_name(record.name),
            str(record.version),
            record.build,
            record.subdir,
        ),
    )
    components = [_package_component(record) for record in records]
    refs_by_name = {
        _normalized_name(record.name): component.bom_ref
        for record, component in zip(records, components, strict=True)
    }
    edges, missing_dependency_edges, incomplete_dependency_refs = _dependency_edges(
        records, refs_by_name
    )
    root_dependencies = _root_dependencies(
        environment.requested_packages,
        edges,
        refs_by_name,
    )

    root = _root_component(
        environment,
        missing_dependency_edges=missing_dependency_edges,
        root_source=(
            "requested-packages"
            if environment.requested_packages
            else "inferred-graph-roots"
        ),
    )
    dependencies = [
        Dependency(
            ref=component.bom_ref,
            dependencies=[
                Dependency(ref=dependency) for dependency in edges[component.bom_ref]
            ],
        )
        for component in components
    ]
    dependencies.append(
        Dependency(
            ref=root.bom_ref,
            dependencies=[
                Dependency(ref=dependency) for dependency in root_dependencies
            ],
        )
    )

    tool = Component(
        type=ComponentType.APPLICATION,
        name="conda-sbom",
        version=__version__,
        bom_ref=f"tool:conda-sbom@{quote(__version__, safe='')}",
        purl=PackageURL(type="pypi", name="conda-sbom", version=__version__),
    )
    bom = Bom(
        serial_number=_PLACEHOLDER_UUID,
        metadata=BomMetaData(
            timestamp=_timestamp(),
            tools=ToolRepository(components=[tool]),
            component=root,
        ),
        components=components,
        dependencies=dependencies,
    )

    document = json.loads(JsonV1Dot7(bom).output_as_string())
    document.pop("serialNumber")
    for dependency in document["dependencies"]:
        dependency.setdefault("dependsOn", [])
    root_composition = {
        "aggregate": (
            "incomplete" if any(environment.external_packages.values()) else "unknown"
        ),
        "assemblies": [root.bom_ref.value],
    }
    if not environment.requested_packages:
        root_composition["dependencies"] = [root.bom_ref.value]
    document["compositions"] = [root_composition]
    if incomplete_dependency_refs:
        document["compositions"].append(
            {
                "aggregate": "incomplete",
                "dependencies": sorted(
                    reference.value for reference in incomplete_dependency_refs
                ),
            }
        )
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def _package_component(record: PackageRecord) -> Component:
    purl = _package_url(record)
    hashes = []
    sha256 = getattr(record, "sha256", None)
    md5 = getattr(record, "md5", None)
    if sha256:
        hashes.append(_hash(HashAlgorithm.SHA_256, sha256, record.name))
    if md5:
        hashes.append(_hash(HashAlgorithm.MD5, md5, record.name))

    properties = [
        Property(name="conda:package:build", value=record.build),
        Property(name="conda:package:build-number", value=str(record.build_number)),
        Property(name="conda:package:subdir", value=record.subdir),
    ]
    channel = _channel_name(record)
    if channel:
        properties.append(Property(name="conda:package:channel", value=channel))
    filename = getattr(record, "fn", None)
    size = getattr(record, "size", None)
    if filename:
        properties.append(Property(name="conda:package:filename", value=filename))
    if size is not None:
        properties.append(Property(name="conda:package:size", value=str(size)))

    external_references = []
    url = getattr(record, "url", None)
    sanitized_url = _sanitize_url(str(url)) if url else None
    if sanitized_url:
        external_references.append(
            ExternalReference(
                type=ExternalReferenceType.DISTRIBUTION,
                url=XsUri(sanitized_url),
            )
        )

    licenses = []
    license_name = getattr(record, "license", None)
    if license_name:
        licenses.append(DisjunctiveLicense(name=license_name))

    return Component(
        type=ComponentType.LIBRARY,
        name=str(record.name),
        version=str(record.version),
        bom_ref=purl.to_string(),
        purl=purl,
        hashes=hashes,
        licenses=licenses,
        external_references=external_references,
        properties=properties,
    )


def _root_component(
    environment: Environment,
    *,
    missing_dependency_edges: int,
    root_source: str,
) -> Component:
    name = environment.name or "conda-environment"
    properties = [
        Property(name="conda:environment:platform", value=environment.platform),
        Property(name="conda:environment:scope", value="resolved-conda-packages"),
        Property(name="conda:environment:root-dependency-source", value=root_source),
    ]
    omitted_external = sum(
        len(packages) for packages in environment.external_packages.values()
    )
    if omitted_external:
        properties.append(
            Property(
                name="conda:environment:external-packages-omitted",
                value=str(omitted_external),
            )
        )
    if environment.virtual_packages:
        properties.append(
            Property(
                name="conda:environment:virtual-packages-omitted",
                value=str(len(environment.virtual_packages)),
            )
        )
    if missing_dependency_edges:
        properties.append(
            Property(
                name="conda:environment:dependency-edges-omitted",
                value=str(missing_dependency_edges),
            )
        )
    return Component(
        type=ComponentType.APPLICATION,
        name=name,
        bom_ref=(
            f"conda-environment:{quote(name, safe='')}"
            f"?platform={quote(environment.platform, safe='')}"
        ),
        properties=properties,
    )


def _package_url(record: PackageRecord) -> PackageURL:
    qualifiers = {
        "build": record.build,
        "subdir": record.subdir,
    }
    channel = _channel_name(record)
    if channel:
        qualifiers["channel"] = channel
    archive_type = _archive_type(getattr(record, "fn", None))
    if archive_type:
        qualifiers["type"] = archive_type
    return PackageURL(
        type="conda",
        name=str(record.name),
        version=str(record.version),
        qualifiers=qualifiers,
    )


def _dependency_edges(
    records: Iterable[PackageRecord],
    refs_by_name: Mapping[str, BomRef],
) -> tuple[dict[BomRef, list[BomRef]], int, set[BomRef]]:
    edges: dict[BomRef, list[BomRef]] = {}
    missing_edges = 0
    incomplete_refs: set[BomRef] = set()
    for record in records:
        record_ref = refs_by_name[_normalized_name(record.name)]
        dependencies = set()
        for dependency in record.depends:
            dependency_name = MatchSpec(dependency).name
            dependency_ref = refs_by_name.get(_normalized_name(dependency_name))
            if dependency_ref is None:
                missing_edges += 1
                incomplete_refs.add(record_ref)
            else:
                dependencies.add(dependency_ref)
        edges[record_ref] = sorted(dependencies, key=lambda ref: ref.value)
    return edges, missing_edges, incomplete_refs


def _root_dependencies(
    requested_packages: Iterable[MatchSpec],
    edges: Mapping[BomRef, list[BomRef]],
    refs_by_name: Mapping[str, BomRef],
) -> list[BomRef]:
    if requested_packages:
        return sorted(
            {
                reference
                for spec in requested_packages
                if (reference := refs_by_name.get(_normalized_name(spec.name)))
                is not None
            },
            key=lambda ref: ref.value,
        )

    incoming = {reference: 0 for reference in edges}
    for dependencies in edges.values():
        for dependency in dependencies:
            incoming[dependency] += 1
    roots = sorted(
        (reference for reference, count in incoming.items() if count == 0),
        key=lambda ref: ref.value,
    )
    reachable = _reachable(roots, edges)
    for reference in sorted(edges, key=lambda ref: ref.value):
        if reference not in reachable:
            roots.append(reference)
            reachable.update(_reachable([reference], edges))
    return roots


def _reachable(
    roots: Iterable[BomRef],
    edges: Mapping[BomRef, list[BomRef]],
) -> set[BomRef]:
    seen: set[BomRef] = set()
    pending = list(roots)
    while pending:
        reference = pending.pop()
        if reference in seen:
            continue
        seen.add(reference)
        pending.extend(edges[reference])
    return seen


def _timestamp() -> datetime:
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch is None:
        return datetime.now(timezone.utc)
    try:
        value = int(epoch)
        if value < 0:
            raise ValueError
        return datetime.fromtimestamp(value, timezone.utc)
    except (OverflowError, OSError, ValueError) as error:
        raise CondaValueError(
            "SOURCE_DATE_EPOCH must be a non-negative integer"
        ) from error


def _hash(algorithm: HashAlgorithm, value: str, package_name: str) -> HashType:
    expected_length = {
        HashAlgorithm.MD5: 32,
        HashAlgorithm.SHA_256: 64,
    }[algorithm]
    if len(value) != expected_length or any(
        character not in hexdigits for character in value
    ):
        raise CondaValueError(
            f"Invalid {algorithm.value} hash for conda package {package_name}"
        )
    return HashType(alg=algorithm, content=value.lower())


def _channel_name(record: PackageRecord) -> str | None:
    channel = record.channel
    name = getattr(channel, "canonical_name", None)
    if not name and channel:
        name = str(channel)
    if name in {None, "", "<unknown>", "unknown"}:
        return None
    name = str(name)
    if urlsplit(name).scheme:
        return _sanitize_url(name)
    return name


def _archive_type(filename: str | None) -> str | None:
    if not filename:
        return None
    if filename.endswith(".conda"):
        return "conda"
    if filename.endswith(".tar.bz2"):
        return "tar.bz2"
    return None


def _sanitize_url(url: str) -> str | None:
    sanitized = remove_auth(split_anaconda_token(url)[0])
    parts = urlsplit(sanitized)
    if not parts.scheme or parts.scheme.lower() == "file":
        return None
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _normalized_name(name: str | None) -> str:
    return str(name or "").lower()
