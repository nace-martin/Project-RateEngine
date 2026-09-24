from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

ACTIVE_FX_RUNTIME = [
    ROOT / "pricing_v4" / "adapter.py",
    ROOT / "pricing_v4" / "engine" / "export_engine.py",
    ROOT / "pricing_v4" / "engine" / "import_engine.py",
]


class TestFxRuntimeGuardrails:
    def test_no_known_fabricated_fx_defaults_in_active_runtime(self):
        forbidden = (
            "Decimal('2.50')",
            'Decimal("2.50")',
            "Decimal('2.78')",
            'Decimal("2.78")',
            "Decimal('0.35')",
            'Decimal("0.35")',
            "Decimal('0.36')",
            'Decimal("0.36")',
            "using 1.0 fallback",
            "defaulting to 1.0",
        )
        for path in ACTIVE_FX_RUNTIME:
            text = path.read_text()
            for value in forbidden:
                assert value not in text, f"Fabricated FX fallback '{value}' remains in {path}"

    def test_no_rate_magnitude_orientation_heuristic_in_active_runtime(self):
        forbidden = (
            "if rate >= 1",
            "if effective_rate >= 1",
            "rate > 1",
            "rate < 1",
        )
        for path in ACTIVE_FX_RUNTIME:
            text = path.read_text()
            for value in forbidden:
                assert value not in text, f"FX orientation heuristic '{value}' remains in {path}"

    def test_adapter_no_longer_reads_quote_fx_from_snapshot_dict(self):
        text = (ROOT / "pricing_v4" / "adapter.py").read_text()
        assert "fx_rates.get(quote_currency" not in text
        assert "tt_buy_from_snapshot" not in text
        assert "tt_sell_from_snapshot" not in text

    def test_legacy_fxrate_not_used_by_active_writer_or_admin_paths(self):
        paths = [
            ROOT / "core" / "fx_views.py",
            ROOT / "core" / "fx.py",
            ROOT / "core" / "admin.py",
            ROOT / "core" / "management" / "commands" / "fetch_fx.py",
        ]
        for path in paths:
            text = path.read_text()
            assert "FxRate" not in text, f"Legacy FxRate runtime reference remains in {path}"
