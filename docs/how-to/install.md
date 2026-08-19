# Run conda-sboms from source

`conda-sboms` must be installed in the Python environment that owns the
`conda` executable. Conda discovers exporter plugins from that environment. A
plugin installed in an unrelated named environment is not available to the
other `conda` executable.

:::{warning}
There is no supported end-user installation yet. `conda-sboms` has no PyPI or
conda package release. Do not install an unpublished package name into a
working base environment.
:::

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

The help output should list:

```text
- cyclonedx-json-v1.7 (aliases: cyclonedx-json, cyclonedx, cdx-json): *.cdx.json
```

Run commands through the same environment:

```console
pixi run --locked -e dev conda export \
  --prefix /path/to/environment \
  --format cyclonedx-json \
  --file environment.cdx.json
```

## Wait for a supported installation

A normal installation command will be documented after `conda-sboms` is
published. At that point, install the plugin into the environment that owns
`conda` and confirm discovery with `conda export --help`.
