# conda-sboms

`conda-sboms` adds CycloneDX software bill of materials (SBOM) export to
`conda export`. It currently emits CycloneDX 1.7 JSON for a resolved conda
environment.

The project is alpha software. No package release has been published yet. The
[installation guide](https://jezdez.github.io/conda-sboms/how-to/install/)
explains how to run it from source without changing a normal conda
installation.

## Use

After the plugin is installed in the environment that owns `conda`, export an
installed environment by name:

```console
conda export --name my-environment --from-history \
  --format cyclonedx-json \
  --file my-environment.cdx.json
```

`--from-history` asks conda to preserve the requested package roots when its
history contains them. The SBOM still contains every resolved conda package.

## What it records

The exporter represents the environment as the root application and each exact
conda package record as a library component. It includes available package
hashes, build and platform data, license text, sanitized distribution URLs,
conda package URLs, and dependency edges.

## Limitations

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
