from app.services.fx import convert_from_eur, convert_to_eur


def test_from_eur_multiplies_rate():
    assert convert_from_eur(100, 0.85) == 85.0
    assert convert_from_eur(0, 0.85) == 0.0
    assert convert_from_eur(None, 0.85) is None


def test_to_eur_divides_rate():
    assert convert_to_eur(85, 0.85) == 100.0
    assert convert_to_eur(0, 0.85) == 0.0
    assert convert_to_eur(None, 0.85) is None


def test_per_kwh_roundtrip_keeps_four_places():
    eur_rate = 0.31
    display = convert_from_eur(eur_rate, 0.86, places=4)
    back = convert_to_eur(display, 0.86, places=4)
    assert back is not None
    assert abs(back - eur_rate) < 0.0002
