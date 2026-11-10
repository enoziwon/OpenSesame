from src.model.llm import LLMClassifier, parse_tool_output


def test_invalid_allergen_becomes_unknown():
    raw = {"results": [{"ingredient": "코코넛", "matches": [{"allergen": "coconut", "verdict": "confirmed"}], "source_unknown": False}]}
    out = parse_tool_output(raw)
    assert out[0].matches == [] and out[0].source_unknown is True


def test_classifier_sends_names_only():
    seen = {}

    def fake_call(system, user):
        seen["user"] = user
        return {"results": [{"ingredient": "참기름", "matches": [{"allergen": "sesame", "verdict": "confirmed"}], "source_unknown": False}]}

    clf = LLMClassifier(call=fake_call, model="fake")
    out = clf.classify(["참기름"])
    assert out[0].matches[0].allergen.value == "sesame"
    assert "참기름" in seen["user"]


def test_garbage_output_is_empty():
    assert parse_tool_output({"oops": 1}) == []
    assert parse_tool_output("not a dict") == []
