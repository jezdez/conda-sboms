# conda-sboms

Generate a CycloneDX software bill of materials (SBOM) for an existing conda
environment.

`conda-sboms` is an exporter plugin for `conda`. It adds the `cyclonedx-json`
format to `conda export` and writes conda's exact package records and dependency
graph as CycloneDX 1.7 JSON. Because it uses conda's standard exporter hook,
clients such as conda-workspaces can use the same format.

The project is alpha software. Questions, bug reports, and contributions are
[welcome on GitHub](https://github.com/jezdez/conda-sboms).

## Quick start

`conda-sboms` requires conda 26.3 or newer. conda 26.5 and newer include the
[`conda-pypi`](https://conda.github.io/conda-pypi/quickstart/) plugin. For a
standard conda installation, activate `base` and install `conda-sboms` from
PyPI as a conda package:

```console
conda activate base
conda pypi install conda-sboms
```

If `conda pypi` is not available, follow the
[installation guide](https://jezdez.github.io/conda-sboms/how-to/install/) to
install the wheel with pip.

Generate an SBOM for an installed environment:

```console
conda export --name my-environment --from-history \
  --format cyclonedx-json \
  --file my-environment.cdx.json
```

`--from-history` asks conda to preserve the requested package roots when its
history contains them. The SBOM still contains every resolved conda package.

For a disposable example, follow the
[getting-started tutorial](https://jezdez.github.io/conda-sboms/tutorials/getting-started/).
The [installation guide](https://jezdez.github.io/conda-sboms/how-to/install/)
also covers source checkouts.

## What the SBOM contains

The environment is represented as the root application and each resolved conda
package as a library component. When available, the SBOM includes package
hashes, build and platform data, license text, sanitized distribution URLs,
conda package URLs, and dependency relationships.

## Scope and limitations

The exporter does not inspect package contents, discover vendored or statically
linked software, include packages from other ecosystems, identify a
manufacturer, scan for vulnerabilities, or establish Cyber Resilience Act
conformity. The root composition marks overall coverage as unproven.
Conda-specific properties record known external-package, virtual-package, and
missing-dependency counts supplied by the input.

Read the [documentation](https://jezdez.github.io/conda-sboms/) for the format
reference, conda-workspaces integration, reproducible output, and coverage
limits.

## Development

Install the locked development environment and confirm that conda discovers the
exporter:

```console
pixi install --locked -e dev
pixi run --locked -e dev conda export --help
```

Run the checks and documentation build:

```console
pixi run --locked -e dev check
pixi run --locked -e docs docs
```

## License

BSD-3-Clause. See [LICENSE](LICENSE).
