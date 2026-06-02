from sales_agent.campaign import Campaign
from sales_agent.instructions import build_instructions

def _campaign(**over):
    base = dict(
        product={"name": "AcmeCRM", "one_liner": "Sets itself up fast.", "price": "$29"},
        persona={"name": "Alex", "role": "rep at Acme", "tone": "warm", "voice": "marin"},
        goal={"type": "book_follow_up", "success": "callback booked"},
        opening_line="Hi {name}, it's Alex.",
        disclosure="if_asked",
        guardrails=["Never invent features."],
        body="## Pitch\nReplaces spreadsheets.",
    )
    base.update(over)
    return Campaign(**base)

def test_includes_persona_goal_guardrails_and_product():
    out = build_instructions(_campaign(), lead_name="Dana")
    assert "Alex" in out
    assert "book" in out.lower()
    assert "Never invent features." in out
    assert "AcmeCRM" in out
    assert "Replaces spreadsheets." in out
    assert "Dana" in out

def test_disclosure_if_asked_vs_upfront_differ():
    asked = build_instructions(_campaign(disclosure="if_asked"), lead_name="Dana")
    upfront = build_instructions(_campaign(disclosure="upfront"), lead_name="Dana")
    assert asked != upfront
    assert "if asked" in asked.lower()
    assert "state" in upfront.lower() and "ai" in upfront.lower()

def test_mentions_both_tools():
    out = build_instructions(_campaign(), lead_name="Dana")
    assert "book_slot" in out
    assert "log_outcome" in out

def test_opening_line_placeholder_filled():
    out = build_instructions(_campaign(opening_line="Hello {name}!"), lead_name="Dana")
    assert "Hello Dana!" in out
    assert "{name}" not in out

def test_accent_included_when_set():
    persona = {"name": "Alex", "role": "rep", "tone": "warm", "voice": "marin", "accent": "Australian"}
    out = build_instructions(_campaign(persona=persona), lead_name="Dana")
    assert "natural Australian accent" in out

def test_accent_absent_when_not_set():
    out = build_instructions(_campaign(), lead_name="Dana")
    assert "accent" not in out.lower()
