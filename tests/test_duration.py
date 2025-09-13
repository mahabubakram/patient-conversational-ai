import pytest
from app.nlu.extractor import extract

@pytest.mark.parametrize("text,expected", [
    ("Fever for 48 hours", 2.0),
    ("Headache for 3 days", 3.0),
    ("Cough for 2 weeks", 14.0),
    ("Since yesterday sore throat", 1.0),
    ("Today I have a cough", 0.5),
    ("A few days of congestion", 3.0),
    ("couple of days nausea", 3.0),
    ("12h of fever", 0.5),
    ("no duration mentioned", None),
])
def test_parse_duration_days(text, expected):
    ext = extract(text)
    if expected is None:
        assert ext.duration_days is None
    else:
        assert ext.duration_days == pytest.approx(expected, rel=1e-3)
