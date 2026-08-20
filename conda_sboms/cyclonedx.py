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
from cyclonedx.model.contact import OrganizationalContact, OrganizationalEntity
from cyclonedx.model.license import DisjunctiveLicense
from cyclonedx.model.tool import ToolRepository
from cyclonedx.output.json import JsonV1Dot7
from packageurl import PackageURL

from . import __version__
from .settings import CycloneDXExportMetadata

if TYPE_CHECKING:
    from typing import Final

    from conda.models.environment import Environment
    from conda.models.records import PackageRecord
    from cyclonedx.model.bom_ref import BomRef

FORMAT: Final = "cyclonedx-json-v1.7"
ALIASES: Final = ("cyclonedx-json", "cyclonedx", "cdx-json")
DEFAULT_FILENAMES: Final = ("*.cdx.json",)
DESCRIPTION: Final = "CycloneDX 1.7 JSON software bill of materials"


class CycloneDXPackage:
    """A resolved conda package represented as a CycloneDX component."""

    def __init__(self, record: PackageRecord) -> None:
        self.record = record

        raw_filename = record.fn
        filename = None
        if raw_filename:
            filename = str(raw_filename).replace("\\", "/").rsplit("/", 1)[-1]
            filename = filename.split("?", 1)[0].split("#", 1)[0] or None

        channel_name = record.channel_name
        if record.channel.scheme == "file" or channel_name in {
            None,
            "",
            "<unknown>",
        }:
            channel_name = None

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
        purl = PackageURL(
            type="conda",
            name=str(record.name),
            version=str(record.version),
            qualifiers=qualifiers,
        )

        hashes = []
        for algorithm, value, expected_length in (
            (HashAlgorithm.SHA_256, record.sha256, 64),
            (HashAlgorithm.MD5, record.md5, 32),
        ):
            if not value:
                continue
            if len(value) != expected_length or any(
                character not in hexdigits for character in value
            ):
                raise CondaValueError(
                    f"Invalid {algorithm.value} hash for conda package {record.name}"
                )
            hashes.append(HashType(alg=algorithm, content=value.lower()))

        properties = [
            Property(name="conda:package:build", value=record.build),
            Property(name="conda:package:build-number", value=str(record.build_number)),
            Property(name="conda:package:subdir", value=record.subdir),
        ]
        if channel_name:
            properties.append(
                Property(name="conda:package:channel", value=channel_name)
            )
        size = getattr(record, "size", None)
        if filename:
            properties.append(Property(name="conda:package:filename", value=filename))
        if size is not None:
            properties.append(Property(name="conda:package:size", value=str(size)))

        external_references = []
        url = str(record.url) if record.url else None
        if url:
            try:
                parts = urlsplit(url)
                is_windows_path = (
                    len(parts.scheme) == 1
                    and len(url) > 2
                    and url[1] == ":"
                    and url[2] in {"/", "\\"}
                )
                if (
                    parts.scheme
                    and parts.scheme.lower() != "file"
                    and not is_windows_path
                ):
                    sanitized = remove_auth(split_anaconda_token(url)[0])
                    parts = urlsplit(sanitized)
                    external_references.append(
                        ExternalReference(
                            type=ExternalReferenceType.DISTRIBUTION,
                            url=XsUri(
                                urlunsplit(
                                    (parts.scheme, parts.netloc, parts.path, "", "")
                                )
                            ),
                        )
                    )
            except ValueError:
                pass

        licenses = []
        if record.license:
            licenses.append(DisjunctiveLicense(name=record.license))

        self.component = Component(
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


class CycloneDXDependencyGraph:
    """Dependency state derived from the resolved conda packages."""

    def __init__(self, packages: list[CycloneDXPackage]) -> None:
        self.references_by_name = {
            package.record.name.lower(): package.component.bom_ref
            for package in packages
        }
        self.components_by_reference = {
            package.component.bom_ref: package.component for package in packages
        }
        self.edges: dict[BomRef, list[BomRef]] = {}
        self.missing_edge_count = 0
        self.incomplete_references: set[BomRef] = set()

        for package in packages:
            record_ref = package.component.bom_ref
            dependencies = set()
            for dependency in package.record.depends:
                dependency_spec = MatchSpec(dependency)
                dependency_name = dependency_spec.name
                dependency_ref = self.references_by_name.get(
                    (dependency_name or "").lower()
                )
                if dependency_ref is None:
                    self.missing_edge_count += 1
                    self.incomplete_references.add(record_ref)
                else:
                    dependencies.add(dependency_ref)
            self.edges[record_ref] = sorted(
                dependencies,
                key=lambda reference: reference.value,
            )

    def root_references(self, requested_packages: list[MatchSpec]) -> list[BomRef]:
        """Choose requested roots or infer roots that cover the whole graph."""
        if requested_packages:
            return sorted(
                {
                    reference
                    for spec in requested_packages
                    if (
                        reference := self.references_by_name.get(
                            (spec.name or "").lower()
                        )
                    )
                    is not None
                },
                key=lambda reference: reference.value,
            )

        incoming = {reference: 0 for reference in self.edges}
        for dependencies in self.edges.values():
            for dependency in dependencies:
                incoming[dependency] += 1
        roots = sorted(
            (reference for reference, count in incoming.items() if count == 0),
            key=lambda reference: reference.value,
        )
        reachable: set[BomRef] = set()
        for reference in [
            *roots,
            *sorted(self.edges, key=lambda item: item.value),
        ]:
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
                pending.extend(self.edges[dependency])
        return roots


class CycloneDXExporter:
    """Build a CycloneDX 1.7 document from a resolved conda environment."""

    def __init__(
        self,
        environment: Environment,
        *,
        metadata: CycloneDXExportMetadata | None = None,
    ) -> None:
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
        self.packages = [CycloneDXPackage(record) for record in records]
        self.graph = CycloneDXDependencyGraph(self.packages)
        self.root_references = self.graph.root_references(
            environment.requested_packages
        )
        self.roots_inferred = not environment.requested_packages
        self.root_completeness = (
            "incomplete" if any(environment.external_packages.values()) else "unknown"
        )

        self.metadata = (
            metadata if metadata is not None else CycloneDXExportMetadata.from_context()
        )
        name = self.metadata.product_name or str(environment.name or "")
        if not self.metadata.product_name and (not name or "/" in name or "\\" in name):
            name = "conda-environment"
        root_source = (
            "inferred-graph-roots" if self.roots_inferred else "requested-packages"
        )
        properties = [
            Property(name="conda:environment:platform", value=environment.platform),
            Property(name="conda:environment:scope", value="resolved-conda-packages"),
            Property(
                name="conda:environment:root-dependency-source",
                value=root_source,
            ),
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
        if self.graph.missing_edge_count:
            properties.append(
                Property(
                    name="conda:environment:dependency-edges-omitted",
                    value=str(self.graph.missing_edge_count),
                )
            )
        identity = quote(name, safe="")
        if self.metadata.product_version:
            identity += f"@{quote(self.metadata.product_version, safe='')}"
        self.root = Component(
            type=ComponentType.APPLICATION,
            name=name,
            version=self.metadata.product_version,
            bom_ref=(
                f"conda-environment:{identity}"
                f"?platform={quote(environment.platform, safe='')}"
            ),
            manufacturer=(
                OrganizationalEntity(
                    name=self.metadata.product_manufacturer,
                    urls=(
                        [XsUri(self.metadata.product_manufacturer_url)]
                        if self.metadata.product_manufacturer_url
                        else None
                    ),
                )
                if self.metadata.product_manufacturer
                else None
            ),
            properties=properties,
        )

        epoch = os.environ.get("SOURCE_DATE_EPOCH")
        if epoch is None:
            self.timestamp = datetime.now(timezone.utc)
        else:
            try:
                value = int(epoch)
                if value < 0:
                    raise ValueError
                self.timestamp = datetime.fromtimestamp(value, timezone.utc)
            except (OverflowError, OSError, ValueError) as error:
                raise CondaValueError(
                    "SOURCE_DATE_EPOCH must be a non-negative integer"
                ) from error

    def export(self) -> str:
        """Serialize the environment as CycloneDX 1.7 JSON."""
        tool = Component(
            type=ComponentType.APPLICATION,
            name="conda-sboms",
            version=__version__,
            bom_ref=f"tool:conda-sboms@{quote(__version__, safe='')}",
            purl=PackageURL(type="pypi", name="conda-sboms", version=__version__),
        )
        components = [package.component for package in self.packages]
        # cyclonedx-python-lib requires a UUID even though it is removed below.
        bom = Bom(
            serial_number=UUID("00000000-0000-4000-8000-000000000000"),
            metadata=BomMetaData(
                timestamp=self.timestamp,
                tools=ToolRepository(components=[tool]),
                component=self.root,
                manufacturer=(
                    OrganizationalEntity(
                        name=self.metadata.author_organization,
                        urls=(
                            [XsUri(self.metadata.author_organization_url)]
                            if self.metadata.author_organization_url
                            else None
                        ),
                    )
                    if self.metadata.author_organization
                    else None
                ),
                authors=(
                    [
                        OrganizationalContact(
                            name=self.metadata.author_name,
                            email=self.metadata.author_email,
                        )
                    ]
                    if self.metadata.author_name
                    else None
                ),
            ),
            components=components,
        )
        for component in components:
            bom.register_dependency(
                component,
                [
                    self.graph.components_by_reference[reference]
                    for reference in self.graph.edges[component.bom_ref]
                ],
            )
        bom.register_dependency(
            self.root,
            [
                self.graph.components_by_reference[reference]
                for reference in self.root_references
            ],
        )

        document = json.loads(JsonV1Dot7(bom).output_as_string())
        document.pop("serialNumber")
        for dependency in document["dependencies"]:
            dependency.setdefault("dependsOn", [])
        root_composition = {
            "aggregate": self.root_completeness,
            "assemblies": [self.root.bom_ref.value],
        }
        if self.roots_inferred:
            root_composition["dependencies"] = [self.root.bom_ref.value]
        document["compositions"] = [root_composition]
        if self.graph.incomplete_references:
            document["compositions"].append(
                {
                    "aggregate": "incomplete",
                    "dependencies": sorted(
                        reference.value
                        for reference in self.graph.incomplete_references
                    ),
                }
            )
        return json.dumps(document, indent=2, sort_keys=True) + "\n"


def export_cyclonedx_json(
    environment: Environment,
    *,
    metadata: CycloneDXExportMetadata | None = None,
) -> str:
    """Export a resolved conda environment as CycloneDX 1.7 JSON."""
    return CycloneDXExporter(environment, metadata=metadata).export()
