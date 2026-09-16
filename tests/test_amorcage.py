"""Vérifie que le paquet est importable et que le marqueur firewall est bien exclu."""

import pytest

import stormshield_utilisateurs


def test_le_paquet_est_importable() -> None:
    assert stormshield_utilisateurs.__doc__ is not None


def test_le_marqueur_firewall_est_exclu_par_defaut() -> None:
    """Ce test échoue si un jour le marqueur cesse d'être exclu par addopts."""
    import subprocess
    import sys

    resultat = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert "test_exige_un_boitier" not in resultat.stdout


@pytest.mark.firewall
def test_exige_un_boitier() -> None:
    """Sentinelle : collectée seulement avec `pytest -m firewall`."""
    raise AssertionError("ce test ne doit jamais tourner sans boîtier")
