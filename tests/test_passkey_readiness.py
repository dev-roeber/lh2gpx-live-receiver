"""Read-only gate tests for the future Passkey/WebAuthn rollout.

These tests deliberately verify absence: no dependency, browser ceremony,
credential route, or activation configuration is allowed in the receiver
before the shared-auth migration is explicitly implemented.
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "app"
REQUIREMENTS = ROOT / "requirements.txt"
SPEC = ROOT / "docs" / "PASSKEY_WEBAUTHN_MIGRATION.md"


def _source_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in SOURCE.rglob("*.py"))


def test_receiver_has_no_passkey_dependency_or_ceremony() -> None:
    source = _source_text().lower()
    requirements = REQUIREMENTS.read_text(encoding="utf-8").lower()

    assert "webauthn" not in requirements
    assert "navigator.credentials" not in source
    assert "generate_registration_options" not in source
    assert "verify_registration_response" not in source
    assert "generate_authentication_options" not in source
    assert "verify_authentication_response" not in source


def test_receiver_has_no_passkey_routes_or_activation_flag() -> None:
    source = _source_text()

    assert "/share/geojson/" not in source
    assert "/api/admin/geojson-shares" not in source
    assert "AUTH_PASSKEY_ENABLED" not in source


def test_passkey_spec_has_fixed_production_origin_and_recovery_gate() -> None:
    spec = SPEC.read_text(encoding="utf-8")

    assert "RP-ID: `devroeber.tail71a8bc.ts.net`" in spec
    assert "https://devroeber.tail71a8bc.ts.net" in spec
    assert "Passwortlogin bleibt verfügbar" in spec
    assert "Mindestens ein getesteter Admin-Passwort-Break-Glass-Weg" in spec
    assert "Passkey-only-Betrieb ist nicht Bestandteil dieser Entscheidung" in spec
