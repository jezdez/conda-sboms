# Produce reproducible output

By default, the SBOM timestamp records the current time. Set
`SOURCE_DATE_EPOCH` to make the timestamp and serialized output repeatable for
an unchanged environment and plugin version.

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

Reproducibility does not promise identical output across different
`conda-sboms` versions. A format update may intentionally change the document.
