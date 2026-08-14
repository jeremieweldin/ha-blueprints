"""Tests for automation/voice-math.yaml.

Layer 1 (recognition): drives each spoken sentence through `hassil`, the exact
matcher Home Assistant's Assist uses, and asserts which operator/number/tail it
extracts — and that unrelated questions are NOT hijacked.

Layer 2 (math): extracts the REAL Jinja response template from the blueprint
YAML, renders it with those slots, and compares the spoken answer against an
independent Python reference evaluator across thousands of randomized chained
expressions (2-5 numbers, digits and words, all four operators, divide-by-zero).

Run:  python -m pytest tests/ -q       (or)   python tests/test_voice_math.py
Requires: hassil, jinja2, pyyaml
"""
import os, sys, random, re
import yaml
from hassil import Intents
from hassil.recognize import recognize
from jinja2 import Environment

HERE = os.path.dirname(os.path.abspath(__file__))
YAML_PATH = os.path.join(HERE, "..", "automation", "voice-math.yaml")

# --------------------------------------------------------------------------- #
# Load the blueprint and extract its response template + default triggers.
# --------------------------------------------------------------------------- #
class HALoader(yaml.SafeLoader):
    pass

# Home Assistant YAML tags we only need to parse past, not resolve.
HALoader.add_constructor("!input", lambda loader, node: ("!input", loader.construct_scalar(node)))
HALoader.add_multi_constructor("!", lambda loader, suffix, node: None)

def load_blueprint():
    with open(YAML_PATH) as f:
        doc = yaml.load(f, Loader=HALoader)
    template = doc["actions"][0]["set_conversation_response"]
    inp = doc["blueprint"]["input"]
    triggers = {
        "+": inp["plus_trigger"]["default"],
        "-": inp["minus_trigger"]["default"],
        "*": inp["times_trigger"]["default"],
        "/": inp["divide_trigger"]["default"],
    }
    dz = inp["divide_by_zero_response"]["default"]
    err = inp["error_response"]["default"]
    return template, triggers, dz, err

TEMPLATE_SRC, TRIGGERS, DZ, ERR = load_blueprint()
JINJA = Environment().from_string(TEMPLATE_SRC)

# Build hassil intents straight from the blueprint's default trigger sentences,
# one intent per operator so we recover which operator matched.
def build_intents():
    intents = {"language": "en",
               "intents": {}, "lists": {"rest": {"wildcard": True}}}
    names = {"+": "Plus", "-": "Minus", "*": "Times", "/": "Divide"}
    for sym, sentences in TRIGGERS.items():
        intents["intents"][names[sym]] = {"data": [{"sentences": sentences}]}
    return Intents.from_dict(intents)

INTENTS = build_intents()
INTENT_OP = {"Plus": "+", "Minus": "-", "Times": "*", "Divide": "/"}

class FakeTrigger:
    def __init__(self, tid, num1, rest):
        self.id = tid
        self.slots = {"num1": num1, "rest": rest}

TID_BY_OP = {"+": "plus", "-": "minus", "*": "times", "/": "divide"}

def run(sentence):
    """Full HA pipeline: recognize -> render the real template. Returns spoken str or None."""
    r = recognize(sentence, INTENTS)
    if not r:
        return None
    op1 = INTENT_OP[r.intent.name]
    trig = FakeTrigger(TID_BY_OP[op1], r.entities["num1"].value, r.entities["rest"].value)
    return JINJA.render(trigger=trig,
                        divide_by_zero_response=DZ, error_response=ERR).strip()

# --------------------------------------------------------------------------- #
# Reference evaluator (independent of the Jinja implementation).
# --------------------------------------------------------------------------- #
UNITS = {'zero':0,'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,
 'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12,'thirteen':13,'fourteen':14,
 'fifteen':15,'sixteen':16,'seventeen':17,'eighteen':18,'nineteen':19}
TENS = {20:'twenty',30:'thirty',40:'forty',50:'fifty',60:'sixty',70:'seventy',80:'eighty',90:'ninety'}
INV_UNITS = {v: k for k, v in UNITS.items()}

def num_to_words(n):
    if n < 20: return INV_UNITS[n]
    if n < 100:
        t = (n // 10) * 10
        return TENS[t] + ('' if n % 10 == 0 else ' ' + INV_UNITS[n % 10])
    if n < 1000:
        h = INV_UNITS[n // 100] + ' hundred'
        return h if n % 100 == 0 else h + ' ' + num_to_words(n % 100)
    if n < 1000000:
        th = num_to_words(n // 1000) + ' thousand'
        return th if n % 1000 == 0 else th + ' ' + num_to_words(n % 1000)
    return str(n)

def ref_eval(nums, ops):
    vals = [nums[0]]; rops = []
    for i, op in enumerate(ops):
        n = nums[i + 1]
        if op == '*': vals[-1] = vals[-1] * n
        elif op == '/':
            if n == 0: return ('divzero', None)
            vals[-1] = vals[-1] / n
        else: rops.append(op); vals.append(n)
    acc = vals[0]
    for i, op in enumerate(rops):
        acc = acc + vals[i + 1] if op == '+' else acc - vals[i + 1]
    return ('ok', acc)

def fmt(x):
    r = round(x, 2)
    return int(r) if r == int(r) else r

def expected_answer(nums, ops):
    kind, val = ref_eval(nums, ops)
    if kind == 'divzero':
        return DZ
    opw = {'+': 'plus', '-': 'minus', '*': 'times', '/': 'divided by'}
    parts = [str(nums[0])]
    for i in range(len(ops)):
        parts += [opw[ops[i]], str(nums[i + 1])]
    return f"{' '.join(parts)} is {fmt(val)}."

# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
FIXED = [
    ("what is 5 plus 3", "5 plus 3 is 8."),
    ("what is 20 minus 4", "20 minus 4 is 16."),
    ("what is 6 times 7", "6 times 7 is 42."),
    ("what is 20 divided by 4", "20 divided by 4 is 5."),
    ("what is 10 divided by 4", "10 divided by 4 is 2.5."),
    ("what is five plus three divided by two times six", "5 plus 3 divided by 2 times 6 is 14."),
    ("calculate 10 divided by 2 plus 3 minus 1 times 4", "10 divided by 2 plus 3 minus 1 times 4 is 4."),
    ("what is one hundred minus forty five", "100 minus 45 is 55."),
    ("what is 5 plus twenty three times 2", "5 plus 23 times 2 is 51."),
    ("what is 2 times 3 times 4 times 5 plus 1", "2 times 3 times 4 times 5 plus 1 is 121."),
    ("what's 20 times 4 minus 2", "20 times 4 minus 2 is 78."),
    ("what is one thousand five hundred plus 2", "1500 plus 2 is 1502."),
    ("what is 100 divided by 0", DZ),
    ("what is 7 plus 2 divided by 0", DZ),
]

# Sentences Assist must LEAVE ALONE (no math trigger).
NON_MATCH = [
    "what is the weather",
    "what is 5 minutes",
    "set a timer for 5 minutes",
    "turn on the lights",
    "what time is it",
]

def test_fixed():
    for sent, exp in FIXED:
        got = run(sent)
        assert got == exp, f"{sent!r}: expected {exp!r}, got {got!r}"

def test_non_match():
    for sent in NON_MATCH:
        got = run(sent)
        assert got is None, f"{sent!r} should not trigger math, got {got!r}"

def test_randomized():
    random.seed(20260814)
    ops_pool = ['+', '-', '*', '/']
    prefixes = ["what is ", "what's ", "calculate ", "compute ", "how much is ", "work out ", ""]
    sym_spoken = {'+': ['plus', 'added to'], '-': ['minus', 'subtract'],
                  '*': ['times', 'multiplied by'], '/': ['divided by', 'over']}

    def rand_num():
        r = random.random()
        if r < 0.6: return random.randint(0, 99)
        if r < 0.85: return random.randint(100, 999)
        if r < 0.97: return random.randint(1000, 99999)
        return random.randint(100000, 1000000)

    failures = []
    N = 6000
    for _ in range(N):
        k = random.randint(1, 4)          # 2..5 numbers
        nums = [rand_num() for _ in range(k + 1)]
        ops = [random.choice(ops_pool) for _ in range(k)]
        use_words = random.random() < 0.5

        def tok(n): return num_to_words(n) if use_words else str(n)
        parts = [tok(nums[0])]
        for i, s in enumerate(ops):
            parts += [random.choice(sym_spoken[s]), tok(nums[i + 1])]
        sent = random.choice(prefixes) + ' '.join(parts)

        got = run(sent)
        exp = expected_answer(nums, ops)
        if got != exp:
            failures.append((sent, exp, got))
            if len(failures) > 10:
                break
    assert not failures, "randomized failures:\n" + "\n".join(
        f"  {s!r}\n    exp {e!r}\n    got {g!r}" for s, e, g in failures)

if __name__ == "__main__":
    test_fixed()
    test_non_match()
    test_randomized()
    print("voice-math: all tests passed")
