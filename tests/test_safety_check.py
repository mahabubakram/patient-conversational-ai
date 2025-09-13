from app.safety.self_check import review

def test_safety_approve_normal():
    draft = {
        "status": "SAFE",
        "message": "Based on what you shared, simple self-care may help.",
        "next_step": "Rest, fluids, analgesia per label.",
        "disclaimer": "This is not a diagnosis; not for emergencies.",
    }
    v = review(draft)
    assert v.action == "APPROVE"

def test_safety_rewrite_missing_disclaimer():
    draft = {
        "status": "SAFE",
        "message": "Looks okay for home care.",
        "next_step": "Rest and fluids.",
        "disclaimer": "",
    }
    v = review(draft)
    assert v.action == "REWRITE"
    assert v.reason == "missing_disclaimer"

def test_safety_block_meds():
    draft = {
        "status": "SAFE",
        "message": "Start antibiotics tonight.",
        "next_step": "Take amoxicillin 500mg.",
        "disclaimer": "This is not a diagnosis; not for emergencies.",
    }
    v = review(draft)
    assert v.action == "BLOCK"

def test_safety_rewrite_diagnostic_claim():
    draft = {
        "status": "SAFE",
        "message": "You have pneumonia.",
        "next_step": "Rest.",
        "disclaimer": "This is not a diagnosis; not for emergencies.",
    }
    v = review(draft)
    assert v.action == "REWRITE"
    assert v.reason == "diagnostic_claim"
    assert isinstance(v.text, str) and "Based on what you shared" in v.text
