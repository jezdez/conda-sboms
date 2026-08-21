# Install conda-sboms

`conda-sboms` must be installed in the Python environment that owns the
`conda` executable. Conda discovers exporter plugins from that environment. A
plugin installed in an unrelated named environment is not available to the
other `conda` executable.

conda 26.3 or newer is required. conda 26.5 and newer include the
[`conda-pypi` plugin](https://conda.github.io/conda-pypi/quickstart/), which can
download the published wheel from PyPI, convert it to a conda package, and
install it into the environment that owns conda.

For a standard conda installation, activate `base` and install the plugin:

```console
conda activate base
conda pypi install "conda-sboms>=0.2.0"
```

`conda pypi install` is pending removal in conda 27.9. If the command is not
available, use the pip method below. The `conda-pypi` channel does not currently
serve `conda-sboms`.

Confirm that the same conda installation discovers the exporter:

```console
conda export --help
```

The help output should list:

```text
- cyclonedx-json-v1.7 (aliases: cyclonedx-json, cyclonedx, cdx-json): *.cdx.json
```

## Install with pip

If `conda pypi` is not available, activate the environment that owns the
`conda` executable and install the same wheel directly:

```console
python -m pip install "conda-sboms>=0.2.0"
```

## Run from a source checkout

Use the repository's locked development environment without modifying a normal
conda installation. Clone the repository:

```console
git clone https://github.com/conda-incubator/conda-sboms.git
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
