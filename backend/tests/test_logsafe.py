from app.services.logsafe import log_safe


def test_newlines_cannot_forge_log_lines():
    assert log_safe("a\nERROR forged\r\nline") == "a ERROR forged  line"


def test_long_values_are_cut_and_non_strings_accepted():
    assert len(log_safe("x" * 5000)) == 500
    assert log_safe(ValueError("boom\nbang")) == "boom bang"
