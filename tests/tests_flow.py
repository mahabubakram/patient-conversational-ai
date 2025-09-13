from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def post(msg, sid="t1"):
    return client.post(f"/api/chat?session_id={sid}", json={"message": msg}).json()

def test_emergency_chest():
    r = post("Crushing chest pain and shortness of breath", sid="e1")
    assert r["status"] == "EMERGENCY"
    assert "disclaimer" in r

def test_urgent_uti():
    r = post("Burning urination with fever and back pain", sid="u1")
    assert r["status"] in ("URGENT", "EMERGENCY")
    assert "disclaimer" in r

def test_strict_age_multi_turn_safe():
    # Turn 1: ask for age
    r1 = post("Dry cough and sore throat for 2 days, no fever", sid="s1")
    assert r1["status"] == "ASK"
    # Turn 2: provide age, same session
    r2 = post("35 years", sid="s1")
    assert r2["status"] == "ASK"
    assert "disclaimer" in r2

def test_infant_fever():
    r = post("My 2 month old has a fever", sid="i1")
    assert r["status"] == "EMERGENCY"
