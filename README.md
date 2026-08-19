# conda-sbom

`conda-sbom` provides software bill of materials exporters for conda.

The first exporter writes CycloneDX 1.7 JSON from a resolved conda
environment. Additional formats, such as SPDX JSON, can be added as separate
exporters without changing conda or conda-workspaces.

## Development

Install the development environment and list the registered exporter:

```console
pixi install
pixi run conda export --help
```

Generate a CycloneDX SBOM from an installed environment:

```console
conda export --name my-environment --from-history \
  --format cyclonedx-json --file my-environment.cdx.json
```

The exporter also works with clients of conda's exporter plugin hook. For
example, conda-workspaces can call it for a selected environment and platform:

```console
conda workspace export --environment default --from-lockfile \
  --platform linux-64 --format cyclonedx-json \
  --file default-linux-64.cdx.json
```

Use `--from-history` when exporting an installed environment so conda can
preserve the requested top-level packages. A resolved workspace lock provides
exact package records, but its current exporter model does not preserve the
manifest's authoritative top-level requirements.

## Scope

The CycloneDX exporter inventories exact conda package records and their
dependency graph. It reports unknown assembly completeness because conda
records do not establish coverage of all vendored or statically linked
software, virtual and system dependencies, or manufacturer metadata. Known
omitted external packages and partial dependency sets are marked incomplete.
The output can contribute to product technical documentation, but it is not by
itself a claim of Cyber Resilience Act conformity.

No accepted conda Enhancement Proposal currently defines an SBOM format or CRA
profile. The initial exporter follows CycloneDX 1.7 and the published conda
package-url type.

## License

BSD-3-Clause. See [LICENSE](LICENSE).
