from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def post(msg, sid):
    return client.post(f"/api/chat?session_id={sid}", json={"message": msg}).json()

def test_followup_order_duration_age_severity():
    # T1: symptoms only -> ask duration
    r1 = post("Dry cough and sore throat, no fever", "ord1")
    assert r1["status"] == "ASK"
    assert "How long" in r1["reply"]

    # T2: give duration -> ask age
    r2 = post("2 days", "ord1")
    assert r2["status"] == "ASK"
    assert "How old" in r2["reply"]

    # T3: give age -> ask severity
    r3 = post("35 years", "ord1")
    assert r3["status"] == "ASK"
    assert "How severe" in r3["reply"]

    # T4: give severity -> SAFE
    r4 = post("mild", "ord1")
    assert r4["status"] == "SAFE"
    assert "disclaimer" in r4
