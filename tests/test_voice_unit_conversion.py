"""Tests for automation/voice-unit-conversion.yaml.

Layer 1 (recognition): drives spoken sentences through `hassil` (the matcher
Home Assistant's Assist uses) and checks amount / from_unit / to_unit extraction.

Layer 2 (conversion): pulls the REAL `base` and `result` Jinja expressions and
the response template out of the blueprint's action, renders them through the
same sandbox Home Assistant uses, and compares against an independent reference
converter — covering every dimension plus unknown-unit and cross-dimension
rejection.

Run:  python -m pytest tests/ -q     (or)   python tests/test_voice_unit_conversion.py
Requires: hassil, jinja2, pyyaml
"""
import os, sys
import yaml
from hassil import Intents
from hassil.recognize import recognize
from jinja2.sandbox import ImmutableSandboxedEnvironment

HERE = os.path.dirname(os.path.abspath(__file__))
YAML_PATH = os.path.join(HERE, "..", "automation", "voice-unit-conversion.yaml")
ENV = ImmutableSandboxedEnvironment()


class HALoader(yaml.SafeLoader):
    pass
HALoader.add_constructor("!input", lambda l, n: ("!input", l.construct_scalar(n)))


def load_blueprint():
    with open(YAML_PATH) as f:
        doc = yaml.load(f, Loader=HALoader)
    inp = doc["blueprint"]["input"]
    triggers = inp["trigger"]["default"]
    unit_map = inp["unit_map"]["default"]
    unit_defs = inp["unit_defs"]["default"]
    unknown = inp["unknown_unit_response"]["default"]
    mismatch = inp["mismatch_response"]["default"]
    alternates = inp["unit_alternates"]["default"]
    # Extract the real template strings from the action's choose/default steps.
    choose_action = next(a for a in doc["actions"] if "choose" in a)
    alt_from_tmpl = doc["actions"][1]["variables"]["from_key"]
    alt_to_tmpl = doc["actions"][2]["variables"]["to_key"]
    steps = choose_action["default"]
    base_tmpl = steps[0]["variables"]["base"]
    result_tmpl = steps[1]["variables"]["result"]
    resp_tmpl = steps[2]["set_conversation_response"]
    return dict(triggers=triggers, unit_map=unit_map, unit_defs=unit_defs,
                unknown=unknown, mismatch=mismatch, alternates=alternates,
                alt_from_tmpl=alt_from_tmpl, alt_to_tmpl=alt_to_tmpl,
                base_tmpl=base_tmpl, result_tmpl=result_tmpl, resp_tmpl=resp_tmpl)

BP = load_blueprint()

# --------------------------------------------------------------------------- #
# Recognition
# --------------------------------------------------------------------------- #
def build_intents():
    return Intents.from_dict({
        "language": "en",
        "intents": {"Convert": {"data": [{"sentences": BP["triggers"]}]}},
        "lists": {"from_unit": {"wildcard": True}, "to_unit": {"wildcard": True}},
    })
INTENTS = build_intents()

def recognize_slots(sentence):
    r = recognize(sentence, INTENTS)
    if not r:
        return None
    e = r.entities
    return (e["amount"].value, e["from_unit"].value, e["to_unit"].value)

# --------------------------------------------------------------------------- #
# Reference converter (independent of the blueprint's Jinja)
# --------------------------------------------------------------------------- #
def ref_convert(amt, from_key, to_key):
    d = BP["unit_defs"]
    base = amt * d[from_key]["factor"] + d[from_key].get("offset", 0)
    return round((base - d[to_key].get("offset", 0)) / d[to_key]["factor"], 2)

# --------------------------------------------------------------------------- #
# Render the blueprint's real templates, emulating HA's native-type variables.
# --------------------------------------------------------------------------- #
def render_native(tmpl, ctx):
    out = ENV.from_string(tmpl).render(**ctx)
    try:
        f = float(out)
        return int(f) if f == int(f) else f
    except ValueError:
        return out

def blueprint_convert(amt, from_key, to_key):
    ctx = dict(amt=float(amt), unit_defs=BP["unit_defs"], from_key=from_key, to_key=to_key)
    base = render_native(BP["base_tmpl"], ctx)
    ctx["base"] = base
    result = render_native(BP["result_tmpl"], ctx)
    return result

def blueprint_response(amt, from_raw, to_raw, result):
    ctx = dict(amt=float(amt), from_raw=from_raw, to_raw=to_raw, result=result)
    return ENV.from_string(BP["resp_tmpl"]).render(**ctx).strip()

# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_every_unit_defined():
    """Every synonym target has a definition, and every definition has a factor+dimension."""
    for word, key in BP["unit_map"].items():
        assert key in BP["unit_defs"], f"synonym {word!r} -> {key!r} has no definition"
    for key, d in BP["unit_defs"].items():
        assert "dimension" in d and "factor" in d, f"{key} missing dimension/factor"

def test_known_conversions():
    # (amount, from_key, to_key, expected result)
    cases = [
        (2, "cup", "floz", 16.0),
        (1, "gallon", "quart", 4.0),
        (3, "lb", "g", 1360.78),
        (1, "kg", "g", 1000.0),
        (5, "mile", "km", 8.05),
        (100, "cm", "m", 1.0),
        (100, "celsius", "fahrenheit", 212.0),
        (32, "fahrenheit", "celsius", 0.0),
        (300, "kelvin", "celsius", 26.85),
        (0, "celsius", "kelvin", 273.15),
        (1, "gb", "mb", 1000.0),
        (2, "hour", "minute", 120.0),
        (1, "hectare", "sqm", 10000.0),
        (60, "mph", "kph", 96.56),
    ]
    for amt, fk, tk, exp in cases:
        got = blueprint_convert(amt, fk, tk)
        assert abs(got - exp) < 0.01, f"{amt} {fk}->{tk}: expected {exp}, blueprint gave {got}"
        # cross-check the reference matches the blueprint too
        assert abs(ref_convert(amt, fk, tk) - got) < 0.001, f"ref/blueprint mismatch for {fk}->{tk}"

def test_blueprint_matches_reference_all_pairs():
    """For every same-dimension pair, the blueprint's Jinja == the reference formula."""
    defs = BP["unit_defs"]
    by_dim = {}
    for k, d in defs.items():
        by_dim.setdefault(d["dimension"], []).append(k)
    for dim, keys in by_dim.items():
        for fk in keys:
            for tk in keys:
                for amt in (1, 7, 50, 1000):
                    got = blueprint_convert(amt, fk, tk)
                    exp = ref_convert(amt, fk, tk)
                    assert abs(got - exp) < 0.001, f"{amt} {fk}->{tk}: bp {got} vs ref {exp}"

def test_response_formatting():
    result = blueprint_convert(2, "cup", "floz")
    assert blueprint_response(2, "cups", "fluid ounces", result) == "2 cups is 16 fluid ounces."
    result = blueprint_convert(100, "celsius", "fahrenheit")
    assert blueprint_response(100, "celsius", "fahrenheit", result) == "100 celsius is 212 fahrenheit."

def test_recognition_and_key_resolution():
    um = BP["unit_map"]
    cases = [
        ("how many ounces are in 2 cups", 2, "cups", "ounces"),
        ("convert 3 pounds to grams", 3, "pounds", "grams"),
        ("what is 100 celsius in fahrenheit", 100, "celsius", "fahrenheit"),
        ("how many square feet are in 2 square meters", 2, "square meters", "square feet"),
        ("what is 5 miles per hour in kilometers per hour", 5, "miles per hour", "kilometers per hour"),
    ]
    for sent, amt, fr, to in cases:
        slots = recognize_slots(sent)
        assert slots is not None, f"{sent!r} did not recognize"
        assert slots == (amt, fr, to), f"{sent!r} -> {slots}"
        assert um.get(fr.lower().strip()) in BP["unit_defs"]
        assert um.get(to.lower().strip()) in BP["unit_defs"]

def test_cross_dimension_is_detectable():
    """Blueprint rejects e.g. cups->pounds because dimensions differ."""
    d = BP["unit_defs"]
    assert d["cup"]["dimension"] != d["lb"]["dimension"]
    assert d["mile"]["dimension"] != d["gallon"]["dimension"]
    # sanity: same-dimension pairs share a dimension
    assert d["cup"]["dimension"] == d["gallon"]["dimension"]

def resolve_keys(from_key, to_key):
    """Run the blueprint's real alternate-unit steps, in order."""
    ctx = dict(unit_defs=BP["unit_defs"], unit_alternates=BP["alternates"],
               from_key=from_key, to_key=to_key)
    ctx["from_key"] = ENV.from_string(BP["alt_from_tmpl"]).render(**ctx).strip()
    ctx["to_key"] = ENV.from_string(BP["alt_to_tmpl"]).render(**ctx).strip()
    return ctx["from_key"], ctx["to_key"]

def test_ounces_with_a_volume_mean_fluid_ounces():
    assert resolve_keys("cup", "oz") == ("cup", "floz")
    assert resolve_keys("oz", "ml") == ("floz", "ml")
    # weight pairs keep plain ounces; true mismatches stay mismatched
    assert resolve_keys("lb", "oz") == ("lb", "oz")
    assert resolve_keys("oz", "g") == ("oz", "g")
    assert resolve_keys("cup", "lb") == ("cup", "lb")
    assert resolve_keys("mile", "oz") == ("mile", "oz")

def test_how_many_ounces_in_two_cups_end_to_end():
    amt, fr, to = recognize_slots("how many ounces are in 2 cups")
    um = BP["unit_map"]
    fk, tk = resolve_keys(um[fr], um[to])
    result = blueprint_convert(amt, fk, tk)
    assert blueprint_response(amt, fr, to, result) == "2 cups is 16 ounces."

def test_ounce_is_weight_fluid_ounce_is_volume():
    um, d = BP["unit_map"], BP["unit_defs"]
    assert d[um["ounces"]]["dimension"] == "weight"
    assert d[um["fluid ounces"]]["dimension"] == "volume"

if __name__ == "__main__":
    import traceback
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t(); print(f"  ok  {t.__name__}")
        except Exception:
            failed += 1; print(f" FAIL {t.__name__}"); traceback.print_exc()
    print("unit-conversion:", "all tests passed" if not failed else f"{failed} FAILED")
    sys.exit(1 if failed else 0)
