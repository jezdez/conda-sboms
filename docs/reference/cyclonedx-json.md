# CycloneDX JSON exporter

The exporter accepts one resolved conda environment and returns a CycloneDX 1.7
JSON document ending with a newline.

## Format identity

| Field | Value |
| --- | --- |
| Distribution | `conda-sboms` |
| Conda plugin entry point | `conda-sboms` |
| Canonical format name | `cyclonedx-json-v1.7` |
| Aliases | `cyclonedx-json`, `cyclonedx`, `cdx-json` |
| Default filename pattern | `*.cdx.json` |
| Specification | CycloneDX 1.7 JSON |
| Platform support | One platform per document |

The canonical name is pinned to CycloneDX 1.7 and will not change meaning. The
unversioned `cyclonedx-json` alias may advance to a later supported CycloneDX
JSON version. Use the canonical name in automation that must remain on 1.7.

All four format names select the same exporter. A filename ending in
`.cdx.json` lets conda detect the format without `--format`:

```console
conda export --name my-environment --file my-environment.cdx.json
```

A custom filename requires the explicit format name:

```console
conda export --name my-environment \
  --format cyclonedx-json \
  --file inventory.json
```

Omit `--file` to write the document to standard output. `conda-sboms` does not
add a separate command-line interface.

## Input contract

The exporter receives one `conda.models.environment.Environment` through
conda's `conda_environment_exporters` hook. `explicit_packages` must contain at
least one exact `PackageRecord`. The callback does not solve an environment,
read a prefix, read a lockfile, or access the network.

Conda and other clients construct the `Environment` before invoking the
exporter. This is why installed prefixes and resolved workspace locks work but
an unresolved list of requirements does not.

## Document metadata

| CycloneDX field | Source |
| --- | --- |
| `$schema` | CycloneDX 1.7 JSON schema URL |
| `bomFormat` | `CycloneDX` |
| `specVersion` | `1.7` |
| `version` | `1` for each newly generated document |
| `metadata.timestamp` | Current UTC time or `SOURCE_DATE_EPOCH` |
| `metadata.tools.components` | `conda-sboms` and its installed version |
| `metadata.component` | The exported conda environment |

The optional `serialNumber` is omitted so unchanged inputs can produce
byte-for-byte identical output.

## Root component

The environment is an `application` component. A safe logical environment name
is preserved. A path-shaped name from `conda export --prefix` becomes
`conda-environment` so the document does not expose the local prefix.

The root has these properties:

| Property | Meaning |
| --- | --- |
| `conda:environment:platform` | Conda subdir represented by the document |
| `conda:environment:scope` | Always `resolved-conda-packages` |
| `conda:environment:root-dependency-source` | `requested-packages` or `inferred-graph-roots` |
| `conda:environment:external-packages-omitted` | Count of known non-conda packages not represented |
| `conda:environment:virtual-packages-omitted` | Count of virtual packages not represented as components |
| `conda:environment:dependency-edges-omitted` | Count of declared dependency edges whose target is absent from the records |

The three omission properties appear only when their count is nonzero.

## Package components

Each exact conda package record becomes a `library` component.

| CycloneDX field | Conda record data |
| --- | --- |
| `name`, `version` | Package name and version |
| `bom-ref`, `purl` | Conda package URL with available build, channel, subdir, and archive type qualifiers |
| `hashes` | Available SHA-256 and MD5 archive hashes |
| `licenses` | Raw conda license text represented as a named license |
| `externalReferences` | Sanitized remote package URL with type `distribution` |
| `properties` | Build string, build number, subdir, canonical channel, filename, and archive size when available |

License text is not treated as an SPDX expression because legacy conda records
may contain arbitrary text. A channel is not treated as the package supplier,
producer, or manufacturer.

## Dependency graph

Package edges come from `PackageRecord.depends`. Each dependency MatchSpec is
matched by package name to the resolved record. `constrains` entries are not
dependencies and are not mapped.

The document contains one dependency entry for the root and one for every
package component. Known leaves have an explicit empty `dependsOn` array.

When `requested_packages` is non-empty, names also present in the resolved
records become root dependencies. Requested names absent from the records are
silently omitted and do not currently produce an incompleteness marker.
Otherwise the exporter infers graph roots and adds a stable representative for
any disconnected cycle so every serialized component is reachable from the
root.

## Completeness

The root assembly composition is `unknown` when conda metadata cannot establish
whether all product constituents are represented. It is `incomplete` when the
input reports omitted external packages.

When roots are inferred, the root reference is also listed under `dependencies`
in the root composition. It uses the same aggregate as the assembly, normally
`unknown`, or `incomplete` when external packages were reported. A package with
a declared dependency absent from the resolved record set appears in a separate
`incomplete` dependency composition.

## Privacy behavior

The exporter removes basic authentication, Anaconda token path segments, query
strings, and fragments from remote distribution URLs. Channel identity comes
from conda's canonical channel name. Local file URLs, local file channels, and
local environment paths are omitted. Package filenames are reduced to their
basename before serialization.

## Errors

The exporter explicitly rejects:

- input without exact package records
- a supplied SHA-256 or MD5 value has the wrong length or contains non-hex data
- `SOURCE_DATE_EPOCH` is negative, malformed, or outside the platform's
  supported timestamp range

Failures occur before conda writes the output returned by the exporter.
