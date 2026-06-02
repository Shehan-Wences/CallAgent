import textwrap
import pytest
from sales_agent.campaign import load_campaign, Campaign, CampaignError

def _write(tmp_path, text):
    p = tmp_path / "c.md"
    p.write_text(textwrap.dedent(text))
    return p

VALID = """\
    ---
    product:
      name: "AcmeCRM"
      one_liner: "A CRM that sets itself up in 10 minutes."
      price: "$29/user/month"
    persona:
      name: "Alex"
      role: "sales rep at Acme"
      tone: "warm, concise"
      voice: "cedar"
    goal:
      type: book_follow_up
      success: "a callback is booked"
    disclosure: if_asked
    guardrails:
      - "Never invent features."
    opening_line: "Hi, am I speaking with {name}?"
    ---
    ## Pitch
    AcmeCRM replaces spreadsheets.
    """

def test_loads_all_fields(tmp_path):
    c = load_campaign(_write(tmp_path, VALID))
    assert c.product["name"] == "AcmeCRM"
    assert c.persona["name"] == "Alex"
    assert c.persona["voice"] == "cedar"
    assert c.goal["type"] == "book_follow_up"
    assert c.disclosure == "if_asked"
    assert c.guardrails == ["Never invent features."]
    assert c.opening_line == "Hi, am I speaking with {name}?"
    assert "AcmeCRM replaces spreadsheets." in c.body

def test_defaults_applied(tmp_path):
    minimal = """\
        ---
        product:
          name: "Widget"
        persona:
          name: "Sam"
        goal:
          type: book_follow_up
        opening_line: "Hello {name}"
        ---
        """
    c = load_campaign(_write(tmp_path, minimal))
    assert c.persona["voice"] == "marin"
    assert c.disclosure == "if_asked"
    assert c.guardrails == []
    assert c.body == ""

@pytest.mark.parametrize("missing_key,doc", [
    ("product.name", '---\npersona:\n  name: "S"\ngoal:\n  type: book_follow_up\nopening_line: "hi"\n---\n'),
    ("persona.name", '---\nproduct:\n  name: "W"\ngoal:\n  type: book_follow_up\nopening_line: "hi"\n---\n'),
    ("goal.type", '---\nproduct:\n  name: "W"\npersona:\n  name: "S"\nopening_line: "hi"\n---\n'),
    ("opening_line", '---\nproduct:\n  name: "W"\npersona:\n  name: "S"\ngoal:\n  type: book_follow_up\n---\n'),
])
def test_missing_required_field_raises_named_error(tmp_path, missing_key, doc):
    p = tmp_path / "c.md"
    p.write_text(doc)
    with pytest.raises(CampaignError) as exc:
        load_campaign(p)
    assert missing_key in str(exc.value)

def test_missing_front_matter_raises(tmp_path):
    p = tmp_path / "c.md"
    p.write_text("no front matter here")
    with pytest.raises(CampaignError):
        load_campaign(p)
