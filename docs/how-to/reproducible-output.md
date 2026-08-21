# Produce reproducible output

By default, the SBOM timestamp records the current time. Preserve a meaningful
timestamp with `SOURCE_DATE_EPOCH`, or omit the timestamp through the public
Python API.

## Preserve a stable timestamp

Choose a non-negative Unix timestamp and export the environment.

::::{tab-set}

:::{tab-item} POSIX

```console
SOURCE_DATE_EPOCH=1720000000 conda export \
  --name my-environment \
  --from-history \
  --format cyclonedx-json \
  --file my-environment.cdx.json
```

:::

:::{tab-item} PowerShell

```powershell
$env:SOURCE_DATE_EPOCH = "1720000000"
conda export `
  --name my-environment `
  --from-history `
  --format cyclonedx-json `
  --file my-environment.cdx.json
```

:::

::::

The exporter sorts components, dependency entries, dependency targets, and JSON
keys. It omits the optional random CycloneDX serial number. With the same
`Environment` input, including requested, external, and virtual packages, the
same environment name and platform, the same product and author metadata, the
same exporter and serializer versions, and the same epoch, a second export is
byte-for-byte identical.

The value must be an integer greater than or equal to zero. An invalid,
negative, or unrepresentable timestamp fails the export instead of silently
using the current time.

## Omit the timestamp

Clients that expose a reproducible-output option can omit time-based metadata
through the public API:

```python
from conda_sboms.cyclonedx import export_cyclonedx_json

document = export_cyclonedx_json(
    environment,
    output_reproducible=True,
)
```

Explicit reproducible mode takes precedence over `SOURCE_DATE_EPOCH`. It omits
the optional CycloneDX `metadata.timestamp` field instead of synthesizing a
timestamp and records `cdx:reproducible=true` in `metadata.properties`. Use
`SOURCE_DATE_EPOCH` when consumers require a timestamp. Stock `conda export`
continues to use `SOURCE_DATE_EPOCH` because conda's exporter hook cannot pass
format-specific options.

Reproducibility does not promise identical output across different
`conda-sboms` versions. A format update may intentionally change the document.
