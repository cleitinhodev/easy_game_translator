from egt.glossary import Glossary


def test_replacements_plain_and_regex():
    g = Glossary()
    g.set_data([
        {"find": "rn0w", "replace": "now"},
        {"find": r"\b0(\d)", "replace": r"O\1", "regex": True},
        {"find": "off", "replace": "x", "enabled": False},
    ], [], save=False)
    assert g.apply_replacements("Do it rn0w and 05 off") == "Do it now and O5 off"


def test_replace_literal_backslash():
    g = Glossary()
    g.set_data([{"find": "a", "replace": "\\1"}], [], save=False)
    assert g.apply_replacements("a") == "\\1"


def test_case_sensitive_rule():
    g = Glossary()
    g.set_data([{"find": "Nina", "replace": "NINA", "case": True}], [], save=False)
    assert g.apply_replacements("nina Nina") == "nina NINA"


def test_protect_restore_roundtrip():
    g = Glossary()
    g.set_data([], ["Nina", "Kael the Bold"], save=False)
    prot, mapping = g.protect("Hello Nina, meet kael the bold!")
    assert "Nina" not in prot and "kael" not in prot.lower()
    assert g.restore(prot.upper().replace("HELLO", "Olá"), mapping).startswith("Olá Nina")
    assert "kael the bold" in g.restore(prot, mapping)


def test_placeholder_is_stable_across_texts():
    g = Glossary()
    g.set_data([], ["Nina", "Kael"], save=False)
    a, _ = g.protect("Nina")
    b, _ = g.protect("hi Nina")
    assert a in b
    # restore sem o mapa também funciona (cache)
    assert g.restore(a) == "Nina"


def test_persistence(tmp_path):
    f = tmp_path / "g.json"
    g = Glossary(f)
    g.set_data([{"find": "x", "replace": "y"}], ["Zed", "zed", ""])
    g2 = Glossary(f)
    assert g2.rules[0]["find"] == "x" and g2.keep == ["Zed"]


def test_bad_regex_ignored():
    g = Glossary()
    g.set_data([{"find": "(", "replace": "", "regex": True}], [], save=False)
    assert g.apply_replacements("(abc") == "(abc"
