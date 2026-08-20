# Add product and author metadata

By default, the root component describes the exported conda environment and the
document identifies only `conda-sboms` as the generating tool. Supply product,
manufacturer, and author values when the environment belongs to a product for
which you can establish those identities.

The settings belong to conda's plugin configuration. They work with
`conda export` and with clients that call the same exporter hook.

## Configure one export

Set the matching `CONDA_PLUGINS_*` variables in a child shell so they cannot
leak into a later export.

::::{tab-set}

:::{tab-item} POSIX

```console
(
  export CONDA_PLUGINS_CONDA_SBOMS_PRODUCT_NAME="Acme Runtime"
  export CONDA_PLUGINS_CONDA_SBOMS_PRODUCT_VERSION="2026.08"
  export CONDA_PLUGINS_CONDA_SBOMS_PRODUCT_MANUFACTURER="Acme GmbH"
  export CONDA_PLUGINS_CONDA_SBOMS_PRODUCT_MANUFACTURER_URL="https://acme.example"
  export CONDA_PLUGINS_CONDA_SBOMS_AUTHOR_NAME="Alice Example"
  export CONDA_PLUGINS_CONDA_SBOMS_AUTHOR_EMAIL="alice@acme.example"
  export CONDA_PLUGINS_CONDA_SBOMS_AUTHOR_ORGANIZATION="Acme Product Security"
  export CONDA_PLUGINS_CONDA_SBOMS_AUTHOR_ORGANIZATION_URL="https://acme.example/security"

  conda export --name my-environment --from-history \
    --format cyclonedx-json \
    --file acme-runtime.cdx.json
)
```

:::

:::{tab-item} PowerShell

```powershell
& (Get-Process -Id $PID).Path -NoProfile -Command {
  $env:CONDA_PLUGINS_CONDA_SBOMS_PRODUCT_NAME = "Acme Runtime"
  $env:CONDA_PLUGINS_CONDA_SBOMS_PRODUCT_VERSION = "2026.08"
  $env:CONDA_PLUGINS_CONDA_SBOMS_PRODUCT_MANUFACTURER = "Acme GmbH"
  $env:CONDA_PLUGINS_CONDA_SBOMS_PRODUCT_MANUFACTURER_URL = "https://acme.example"
  $env:CONDA_PLUGINS_CONDA_SBOMS_AUTHOR_NAME = "Alice Example"
  $env:CONDA_PLUGINS_CONDA_SBOMS_AUTHOR_EMAIL = "alice@acme.example"
  $env:CONDA_PLUGINS_CONDA_SBOMS_AUTHOR_ORGANIZATION = "Acme Product Security"
  $env:CONDA_PLUGINS_CONDA_SBOMS_AUTHOR_ORGANIZATION_URL = "https://acme.example/security"

  conda export --name my-environment --from-history `
    --format cyclonedx-json `
    --file acme-runtime.cdx.json
}
```

:::

::::

The product name and version must be set together. A product manufacturer also
requires both values. An individual author and author organization are
independent and may be supplied separately or together. An author email requires
an individual author name. Each organization URL requires its organization
name.

The product replaces the generic environment identity in
`metadata.component`. Its manufacturer is recorded on that component. The
author organization is recorded as the organization that created the BOM, and
the individual author is recorded in `metadata.authors`. The `conda-sboms` tool
component remains separate.

## Save metadata in conda configuration

Use conda's normal configuration when the same values should apply to every
export made with that configuration:

```console
conda config --set plugins.conda_sboms_product_name "Acme Runtime"
conda config --set plugins.conda_sboms_product_version "2026.08"
conda config --set plugins.conda_sboms_product_manufacturer "Acme GmbH"
conda config --set plugins.conda_sboms_product_manufacturer_url \
  "https://acme.example"
conda config --set plugins.conda_sboms_author_name "Alice Example"
conda config --set plugins.conda_sboms_author_email "alice@acme.example"
conda config --set plugins.conda_sboms_author_organization \
  "Acme Product Security"
conda config --set plugins.conda_sboms_author_organization_url \
  "https://acme.example/security"
```

Inspect the active values before exporting another product:

```console
conda config --show plugins.conda_sboms_product_name
conda config --show plugins.conda_sboms_product_version
conda config --show plugins.conda_sboms_product_manufacturer
conda config --show plugins.conda_sboms_product_manufacturer_url
conda config --show plugins.conda_sboms_author_name
conda config --show plugins.conda_sboms_author_email
conda config --show plugins.conda_sboms_author_organization
conda config --show plugins.conda_sboms_author_organization_url
```

Remove the saved values when they should no longer apply:

```console
conda config --remove-key plugins.conda_sboms_product_name
conda config --remove-key plugins.conda_sboms_product_version
conda config --remove-key plugins.conda_sboms_product_manufacturer
conda config --remove-key plugins.conda_sboms_product_manufacturer_url
conda config --remove-key plugins.conda_sboms_author_name
conda config --remove-key plugins.conda_sboms_author_email
conda config --remove-key plugins.conda_sboms_author_organization
conda config --remove-key plugins.conda_sboms_author_organization_url
```

Clients that invoke conda's registered exporter hook inherit the plugin
configuration present when their process starts. Set the `CONDA_PLUGINS_*`
variables before launching `conda`, `conda workspace`, or another plugin client.

## Pass metadata from Python

Python callers can supply the metadata for one call without changing conda's
active configuration:

```python
from conda_sboms.cyclonedx import export_cyclonedx_json
from conda_sboms.settings import CycloneDXExportMetadata

document = export_cyclonedx_json(
    environment,
    metadata=CycloneDXExportMetadata(
        product_name="Acme Runtime",
        product_version="2026.08",
        product_manufacturer="Acme GmbH",
        product_manufacturer_url="https://acme.example",
        author_name="Alice Example",
        author_email="alice@acme.example",
        author_organization="Acme Product Security",
        author_organization_url="https://acme.example/security",
    ),
)
```

`environment` is the resolved `conda.models.environment.Environment` passed to
an environment exporter. Supplying `CycloneDXExportMetadata` bypasses the
active conda plugin settings for that call.
