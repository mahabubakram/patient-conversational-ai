# tests/test_redflags.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def post(msg, sid):
    return client.post(f"/api/chat?session_id={sid}", json={"message": msg}).json()

def test_emergency_chest_pain_sob():
    r = post("Crushing chest pain and shortness of breath", "rf1")
    assert r["status"] == "EMERGENCY"

def test_emergency_worst_headache():
    r = post("Worst headache of my life", "rf2")
    assert r["status"] == "EMERGENCY"

def test_emergency_fever_stiff_neck():
    r = post("High fever and stiff neck", "rf3")
    assert r["status"] == "EMERGENCY"

def test_emergency_anaphylaxis_combo():
    r = post("I have hives and trouble breathing", "rf4")
    assert r["status"] == "EMERGENCY"

def test_emergency_pregnancy_bleeding():
    r = post("I am pregnant and have severe abdominal pain", "rf5")
    assert r["status"] == "EMERGENCY"

def test_emergency_infant_fever():
    r = post("My 2 month old has a fever", "rf6")
    assert r["status"] == "EMERGENCY"

def test_emergency_overdose():
    r = post("I took too many pills", "rf7")
    assert r["status"] == "EMERGENCY"

def test_emergency_trauma_head_loc():
    r = post("I fell down the stairs and blacked out", "rf8")
    assert r["status"] == "EMERGENCY"

def test_emergency_mental_health():
    r = post("I feel suicidal", "rf9")
    assert r["status"] == "EMERGENCY"

def test_urgent_uti_systemic():
    r = post("Burning urination with fever and back pain", "rf10")
    assert r["status"] in ("URGENT", "EMERGENCY")  # wording may escalate

def test_negation_no_chest_pain():
    r = post("No chest pain, just mild cough", "rf11")
    # Should NOT be emergency; depending on your strict policy, likely ASK
    assert r["status"] in ("ASK", "SAFE", "URGENT")
