from __future__ import annotations

import pytest
from conda.exceptions import CondaValueError

from conda_sboms.settings import CycloneDXExportMetadata


def test_export_metadata_normalizes_values() -> None:
    metadata = CycloneDXExportMetadata(
        product_name="  Acme Runtime  ",
        product_version="  2026.08  ",
        author_name="   ",
    )

    assert metadata.product_name == "Acme Runtime"
    assert metadata.product_version == "2026.08"
    assert metadata.author_name is None


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"product_name": "Acme Runtime"}, "product_version"),
        ({"product_version": "2026.08"}, "product_name"),
        ({"product_manufacturer": "Acme GmbH"}, "product_manufacturer"),
        (
            {"product_name": "Acme Runtime", "product_version": "x" * 1025},
            "must not exceed 1024",
        ),
        (
            {"product_manufacturer_url": "https://acme.example"},
            "product_manufacturer_url",
        ),
        ({"author_email": "alice@acme.example"}, "author_email"),
        (
            {"author_organization_url": "https://acme.example"},
            "author_organization_url",
        ),
        (
            {"author_name": "Alice Example", "author_email": "not-an-email"},
            "valid email address",
        ),
        (
            {
                "product_name": "Acme Runtime",
                "product_version": "2026.08",
                "product_manufacturer": "Acme GmbH",
                "product_manufacturer_url": "file:///private/manufacturer",
            },
            "HTTP or HTTPS URL",
        ),
        (
            {
                "author_organization": "Acme Product Security",
                "author_organization_url": "https://user:secret@acme.example",
            },
            "without credentials",
        ),
        (
            {
                "author_organization": "Acme Product Security",
                "author_organization_url": "https://acme.example/?token=secret",
            },
            "query, or fragment",
        ),
        (
            {
                "author_organization": "Acme Product Security",
                "author_organization_url": "https://acme.example/#private",
            },
            "query, or fragment",
        ),
        (
            {
                "author_organization": "Acme Product Security",
                "author_organization_url": "https://acme.example/%zz",
            },
            "HTTP or HTTPS URL",
        ),
    ],
)
def test_invalid_export_metadata_fails(
    values: dict[str, str],
    message: str,
) -> None:
    with pytest.raises(CondaValueError, match=message):
        CycloneDXExportMetadata(**values)
