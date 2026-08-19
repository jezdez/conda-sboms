# Install conda-sboms

`conda-sboms` must be installed in the Python environment that owns the
`conda` executable. Conda discovers exporter plugins from that environment. A
plugin installed in an unrelated named environment is not available to the
other `conda` executable.

conda 26.3 or newer is required and is not distributed on PyPI. Activate the
environment that already provides conda, then install the plugin:

```console
python -m pip install conda-sboms
```

Confirm that the same conda installation discovers the exporter:

```console
conda export --help
```

The help output should list:

```text
- cyclonedx-json-v1.7 (aliases: cyclonedx-json, cyclonedx, cdx-json): *.cdx.json
```

## Run from a source checkout

Use the repository's locked development environment without modifying a normal
conda installation. Clone the repository:

```console
git clone https://github.com/jezdez/conda-sboms.git
cd conda-sboms
```

Install the development environment and inspect the registered formats:

```console
pixi install --locked -e dev
pixi run --locked -e dev conda export --help
```

Run commands through the same environment:

```console
pixi run --locked -e dev conda export \
  --prefix /path/to/environment \
  --format cyclonedx-json \
  --file environment.cdx.json
```
