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

# cyclonedx-python-lib requires a UUID even though the serialized field is removed.
_SERIAL_NUMBER_PLACEHOLDER = UUID("00000000-0000-4000-8000-000000000000")

FORMAT: Final = "cyclonedx-json-v1.7"
ALIASES: Final = ("cyclonedx-json", "cyclonedx", "cdx-json")
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
            record.name.lower(),
            str(record.version),
            record.build,
            record.subdir,
        ),
    )
    components = [_package_component(record) for record in records]
    refs_by_name = {
        record.name.lower(): component.bom_ref
        for record, component in zip(records, components, strict=True)
    }
    edges, missing_dependency_edges, incomplete_dependency_refs = (
        _package_dependency_graph(records, refs_by_name)
    )
    root_dependencies = _root_dependency_refs(
        environment.requested_packages,
        edges,
        refs_by_name,
    )

    root = _root_component(
        environment, missing_dependency_edges=missing_dependency_edges
    )

    tool = Component(
        type=ComponentType.APPLICATION,
        name="conda-sboms",
        version=__version__,
        bom_ref=f"tool:conda-sboms@{quote(__version__, safe='')}",
        purl=PackageURL(type="pypi", name="conda-sboms", version=__version__),
    )
    bom = Bom(
        serial_number=_SERIAL_NUMBER_PLACEHOLDER,
        metadata=BomMetaData(
            timestamp=_creation_timestamp(),
            tools=ToolRepository(components=[tool]),
            component=root,
        ),
        components=components,
    )
    components_by_ref = {component.bom_ref: component for component in components}
    for component in components:
        bom.register_dependency(
            component,
            [components_by_ref[ref] for ref in edges[component.bom_ref]],
        )
    bom.register_dependency(
        root,
        [components_by_ref[ref] for ref in root_dependencies],
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
    """Map one exact conda package record to a CycloneDX component."""
    raw_filename = record.fn
    filename = None
    if raw_filename:
        filename = str(raw_filename).replace("\\", "/").rsplit("/", 1)[-1]
        filename = filename.split("?", 1)[0].split("#", 1)[0] or None
    channel_name = record.channel_name
    if record.channel.scheme == "file" or channel_name in {None, "", "<unknown>"}:
        channel_name = None
    purl = _conda_purl(record, filename, channel_name)
    hashes = []
    sha256 = record.sha256
    md5 = record.md5
    if sha256:
        hashes.append(_validated_hash(HashAlgorithm.SHA_256, sha256, record.name))
    if md5:
        hashes.append(_validated_hash(HashAlgorithm.MD5, md5, record.name))

    properties = [
        Property(name="conda:package:build", value=record.build),
        Property(name="conda:package:build-number", value=str(record.build_number)),
        Property(name="conda:package:subdir", value=record.subdir),
    ]
    if channel_name:
        properties.append(Property(name="conda:package:channel", value=channel_name))
    size = getattr(record, "size", None)
    if filename:
        properties.append(Property(name="conda:package:filename", value=filename))
    if size is not None:
        properties.append(Property(name="conda:package:size", value=str(size)))

    external_references = []
    url = record.url
    sanitized_url = _sanitized_remote_url(str(url)) if url else None
    if sanitized_url:
        external_references.append(
            ExternalReference(
                type=ExternalReferenceType.DISTRIBUTION,
                url=XsUri(sanitized_url),
            )
        )

    licenses = []
    license_name = record.license
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
) -> Component:
    """Describe the exported environment without exposing its local prefix."""
    name = str(environment.name or "")
    if not name or "/" in name or "\\" in name:
        name = "conda-environment"
    root_source = (
        "requested-packages"
        if environment.requested_packages
        else "inferred-graph-roots"
    )
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


def _conda_purl(
    record: PackageRecord,
    filename: str | None,
    channel_name: str | None,
) -> PackageURL:
    """Build the current package-url conda identity in one changeable seam."""
    qualifiers = {
        "build": record.build,
        "subdir": record.subdir,
    }
    if channel_name:
        qualifiers["channel"] = channel_name
    if filename and filename.endswith(".conda"):
        qualifiers["type"] = "conda"
    elif filename and filename.endswith(".tar.bz2"):
        qualifiers["type"] = "tar.bz2"
    return PackageURL(
        type="conda",
        name=str(record.name),
        version=str(record.version),
        qualifiers=qualifiers,
    )


def _package_dependency_graph(
    records: Iterable[PackageRecord],
    refs_by_name: Mapping[str, BomRef],
) -> tuple[dict[BomRef, list[BomRef]], int, set[BomRef]]:
    """Build package edges and identify records with unresolved dependencies."""
    edges: dict[BomRef, list[BomRef]] = {}
    missing_edges = 0
    incomplete_refs: set[BomRef] = set()
    for record in records:
        record_ref = refs_by_name[record.name.lower()]
        dependencies = set()
        for dependency in record.depends:
            dependency_spec = MatchSpec(dependency)
            dependency_name = dependency_spec.name
            dependency_ref = refs_by_name.get((dependency_name or "").lower())
            if dependency_ref is None:
                missing_edges += 1
                incomplete_refs.add(record_ref)
            else:
                dependencies.add(dependency_ref)
        edges[record_ref] = sorted(dependencies, key=lambda ref: ref.value)
    return edges, missing_edges, incomplete_refs


def _root_dependency_refs(
    requested_packages: list[MatchSpec],
    edges: Mapping[BomRef, list[BomRef]],
    refs_by_name: Mapping[str, BomRef],
) -> list[BomRef]:
    """Choose root edges and cover disconnected cycles when roots are inferred."""
    if requested_packages:
        return sorted(
            {
                reference
                for spec in requested_packages
                if (reference := refs_by_name.get((spec.name or "").lower()))
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
    reachable: set[BomRef] = set()
    for reference in [*roots, *sorted(edges, key=lambda ref: ref.value)]:
        if reference in reachable:
            continue
        if reference not in roots:
            roots.append(reference)
        pending = [reference]
        while pending:
            dependency = pending.pop()
            if dependency in reachable:
                continue
            reachable.add(dependency)
            pending.extend(edges[dependency])
    return roots


def _creation_timestamp() -> datetime:
    """Use SOURCE_DATE_EPOCH when the caller requests reproducible output."""
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


def _validated_hash(
    algorithm: HashAlgorithm,
    value: str,
    package_name: str,
) -> HashType:
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


def _sanitized_remote_url(url: str) -> str | None:
    """Strip credentials and mutable URL data, and reject local file URLs."""
    try:
        parts = urlsplit(url)
        is_windows_path = (
            len(parts.scheme) == 1
            and len(url) > 2
            and url[1] == ":"
            and url[2] in {"/", "\\"}
        )
        if not parts.scheme or parts.scheme.lower() == "file" or is_windows_path:
            return None
        sanitized = remove_auth(split_anaconda_token(url)[0])
        parts = urlsplit(sanitized)
    except ValueError:
        return None
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
