import pytest

class TestRateCardAdapter:
    @pytest.mark.xfail
    def test_parser(self):
        # This test will fail until the HTML parser is implemented
        assert False

    @pytest.mark.xfail
    def test_fee_math(self):
        # This test will fail until the fee math is implemented
        assert False
