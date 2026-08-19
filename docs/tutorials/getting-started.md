# Generate your first SBOM

This tutorial creates a small conda environment, exports its resolved package
graph as CycloneDX 1.7 JSON, and inspects the result.

## Prerequisites

- conda 26.5 or newer
- network access to PyPI and your configured conda channels

## Install conda-sboms

```console
conda activate base
conda pypi install conda-sboms
```

Confirm that conda discovered the exporter:

```console
conda export --help
```

The available environment formats should include `cyclonedx-json-v1.7` with the
aliases `cyclonedx-json`, `cyclonedx`, and `cdx-json`.

## Create an environment to describe

Create a local prefix with Python and Requests:

```console
conda create \
  --prefix ./build/tutorial-environment \
  --channel conda-forge \
  --yes \
  python=3.13 requests
```

This command gives conda both the requested packages and the complete solved
package set. The exporter uses both parts of that record.

## Export the SBOM

```console
conda export \
  --prefix ./build/tutorial-environment \
  --from-history \
  --format cyclonedx-json \
  --file build/tutorial-environment.cdx.json
```

`--from-history` asks conda to retain `python` and `requests` as the requested
roots. The exporter still writes every resolved conda package as a component.

## Inspect the document

Print the format, root component, root source, and component count:

```console
python - <<'PY'
import json
from pathlib import Path

path = Path("build/tutorial-environment.cdx.json")
document = json.loads(path.read_text(encoding="utf-8"))
root = document["metadata"]["component"]
properties = {item["name"]: item["value"] for item in root["properties"]}

print(document["bomFormat"], document["specVersion"])
print(root["name"])
print(properties["conda:environment:root-dependency-source"])
print(len(document["components"]), "components")
PY
```

The result reports CycloneDX 1.7, uses `conda-environment` instead of exposing
the local prefix path, and reports `requested-packages` as the root dependency
source. The exact component count depends on the current solve.

Open `build/tutorial-environment.cdx.json` and find the `requests` component.
Its fields include the exact version and build, a conda package URL, available
archive hashes, the sanitized distribution URL, and conda package properties.
The corresponding entry in `dependencies` points to its resolved dependencies.

## Clean up

Remove the tutorial environment and generated SBOM:

```console
conda remove \
  --prefix ./build/tutorial-environment \
  --all \
  --yes
rm build/tutorial-environment.cdx.json
```

## Next steps

- Use the [CycloneDX JSON reference](../reference/cyclonedx-json.md) to interpret
  each field.
- Make repeated exports byte-for-byte stable with
  [reproducible output](../how-to/reproducible-output.md).
- Read [coverage and compliance](../explanation/coverage-and-compliance.md)
  before treating the document as a product inventory.
