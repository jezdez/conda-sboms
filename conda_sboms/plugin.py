from __future__ import annotations

from typing import TYPE_CHECKING

from conda.plugins import hookimpl
from conda.plugins.types import CondaEnvironmentExporter, EnvironmentFormat

if TYPE_CHECKING:
    from collections.abc import Iterable

    from conda.plugins.types import CondaSetting


@hookimpl
def conda_settings() -> Iterable[CondaSetting]:
    from .settings import CycloneDXExportMetadata

    yield from CycloneDXExportMetadata.conda_settings()


@hookimpl
def conda_environment_exporters() -> Iterable[CondaEnvironmentExporter]:
    from . import cyclonedx

    yield CondaEnvironmentExporter(
        name=cyclonedx.FORMAT,
        aliases=cyclonedx.ALIASES,
        default_filenames=cyclonedx.DEFAULT_FILENAMES,
        export=cyclonedx.export_cyclonedx_json,
        description=cyclonedx.DESCRIPTION,
        environment_format=EnvironmentFormat.environment,
    )
