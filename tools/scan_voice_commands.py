#!/usr/bin/env python3
"""
scan_voice_commands.py  (v2 — blueprint-aware)
-----------------------------------------------------------------------
Scans Home Assistant config for automations with a `conversation`
trigger and groups their sentences into dashboard sections.

Handles FOUR sources:
  1. Package files under /config/packages/*.yaml — automations nested
     under a top-level `automation:` key.
  2. /config/automations.yaml — the UI-managed format, a bare YAML
     list of automation dicts (no `automation:` wrapper).
  3. Blueprint-based automations (`use_blueprint:`). These don't carry
     their sentences directly — the scanner follows the blueprint's
     `path` into /config/blueprints/automation/, finds which input
     drives the conversation trigger, and resolves its value from
     either the instance's input overrides or the blueprint's own
     defaults.
  4. Custom sentence files under /config/custom_sentences/<lang>/*.yaml
     (e.g. the one the Voice Timers integration writes). Each file is one
     section, titled from a "# section: Title" comment in its first lines,
     or else from the file name.

Sections are grouped by automation alias: text before the first
" - " becomes the section title (e.g. "Voice Timer - Set named timer"
groups under "Voice Timer"). Keep that naming convention consistent
across your automations or they'll collapse into one bucket.

Outputs JSON to stdout:
{
  "generated_at": "...",
  "sections": [
    {"title": "...", "source_files": [...], "commands": [...]},
    ...
  ]
}

USAGE:
  python3 scan_voice_commands.py [package_dir] [automations_file] [blueprints_dir] [sentences_dir]
  Defaults:
    package_dir       = /config/packages
    automations_file  = /config/automations.yaml
    blueprints_dir    = /config/blueprints/automation
    sentences_dir     = /config/custom_sentences

INSTALL:
  Put this file at /config/scripts/scan_voice_commands.py
-----------------------------------------------------------------------
"""

import sys
import json
import glob
import re
import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    print(json.dumps({"error": "PyYAML not installed. Run: pip3 install pyyaml"}))
    sys.exit(1)


class TolerantLoader(yaml.SafeLoader):
    """Loads HA YAML, treating any unknown tag (!include, !input, !secret,
    Jinja-laced scalars, etc.) as a plain scalar/sequence/mapping instead
    of raising, since we only need structure + text, not live resolution."""
    pass


def _any_tag(loader, tag_suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


TolerantLoader.add_multi_constructor("!", _any_tag)

_blueprint_cache = {}


def load_yaml_safe(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.load(f, Loader=TolerantLoader)
    except Exception as e:
        print(f"warning: failed to parse {path}: {e}", file=sys.stderr)
        return None


def get_triggers(automation_or_blueprint):
    triggers = automation_or_blueprint.get("triggers") or automation_or_blueprint.get("trigger") or []
    if isinstance(triggers, dict):
        triggers = [triggers]
    return triggers


def find_input_default(inputs, key):
    """Recursively search a blueprint's `input:` tree for a leaf entry
    named `key` and return its `default`, however deeply it's nested
    inside collapsible sections."""
    if not isinstance(inputs, dict):
        return None
    for k, v in inputs.items():
        if k == key and isinstance(v, dict) and "default" in v:
            return v["default"]
        if isinstance(v, dict) and isinstance(v.get("input"), dict):
            found = find_input_default(v["input"], key)
            if found is not None:
                return found
    return None


def load_blueprint(path, blueprints_dir):
    if path in _blueprint_cache:
        return _blueprint_cache[path]
    full_path = Path(blueprints_dir) / path
    data = load_yaml_safe(full_path) if full_path.exists() else None
    if data is None:
        # fall back: search recursively by filename in case the path
        # format doesn't match local folder structure
        matches = list(Path(blueprints_dir).rglob(Path(path).name))
        if matches:
            data = load_yaml_safe(matches[0])
    _blueprint_cache[path] = data
    return data


def extract_conversation_commands(automation, blueprints_dir):
    """Return list of command sentences for one automation dict, or
    None if it has no conversation trigger (direct or via blueprint)."""

    if isinstance(automation.get("use_blueprint"), dict):
        bp_ref = automation["use_blueprint"]
        bp_path = bp_ref.get("path")
        overrides = bp_ref.get("input") or {}
        if not bp_path:
            return None
        blueprint = load_blueprint(bp_path, blueprints_dir)
        if not isinstance(blueprint, dict):
            return None

        # A blueprint can have several conversation triggers (e.g. date,
        # time, and both), each fed by its own input.
        trig_keys = []
        for trig in get_triggers(blueprint):
            if not isinstance(trig, dict):
                continue
            ttype = trig.get("trigger") or trig.get("platform")
            if ttype == "conversation" and trig.get("command"):
                trig_keys.append(trig.get("command"))

        commands = []
        for trig_key in trig_keys:
            # instance override takes priority over blueprint default
            if trig_key in overrides:
                val = overrides[trig_key]
            else:
                val = find_input_default(
                    (blueprint.get("blueprint") or {}).get("input", {}), trig_key
                )
            if isinstance(val, list):
                commands.extend(str(v) for v in val)
            elif isinstance(val, str):
                commands.append(val)
        return commands or None

    # direct (non-blueprint) automation
    commands = []
    for trig in get_triggers(automation):
        if not isinstance(trig, dict):
            continue
        ttype = trig.get("trigger") or trig.get("platform")
        if ttype == "conversation":
            cmd = trig.get("command")
            if isinstance(cmd, str):
                commands.append(cmd)
            elif isinstance(cmd, list):
                commands.extend(str(c) for c in cmd)
    return commands or None


def section_title_for(alias, fallback_stem):
    alias = (alias or "").strip()
    if " - " in alias:
        return alias.split(" - ", 1)[0].strip()
    if alias:
        return alias
    return fallback_stem.replace("_", " ").title()


def collect_automations_from_data(data):
    """Handle both the `automation:` wrapped package format and the
    bare-list automations.yaml format."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        automations = data.get("automation")
        if isinstance(automations, dict):
            return [automations]
        if isinstance(automations, list):
            return automations
    return []


def sentence_file_title(path):
    """"# section: Title" in a file's first lines, else its name."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            for _ in range(15):
                m = re.match(r"\s*#\s*section:\s*(.+)", f.readline(), re.IGNORECASE)
                if m:
                    return m.group(1).strip()
    except OSError:
        pass
    return Path(path).stem.replace("_", " ").title()


def extract_sentence_file_commands(data):
    commands = []
    intents = (data or {}).get("intents") if isinstance(data, dict) else None
    if not isinstance(intents, dict):
        return commands
    for intent in intents.values():
        for block in (intent or {}).get("data") or []:
            for sentence in (block or {}).get("sentences") or []:
                commands.append(str(sentence))
    return commands


def readable(command):
    """{vt_minutes:minutes} and {0..10000:num1} read better as {minutes}, {num1}."""
    return re.sub(r"\{[^{}:]+:([^{}]+)\}", r"{\1}", command)


def scan(package_dir, automations_file, blueprints_dir, sentences_dir=None):
    sections = {}  # title -> {"source_files": set, "commands": set}

    def add(title, source_name, commands):
        bucket = sections.setdefault(title, {"source_files": set(), "commands": set()})
        bucket["source_files"].add(source_name)
        for c in commands:
            bucket["commands"].add(readable(c))

    # 1. package files
    paths = sorted(glob.glob(str(Path(package_dir) / "*.yaml"))) + sorted(
        glob.glob(str(Path(package_dir) / "*.yml"))
    )
    for path in paths:
        data = load_yaml_safe(path)
        for auto in collect_automations_from_data(data):
            if not isinstance(auto, dict):
                continue
            commands = extract_conversation_commands(auto, blueprints_dir)
            if not commands:
                continue
            title = section_title_for(auto.get("alias"), Path(path).stem)
            add(title, Path(path).name, commands)

    # 2. automations.yaml (bare list)
    if automations_file and Path(automations_file).exists():
        data = load_yaml_safe(automations_file)
        for auto in collect_automations_from_data(data):
            if not isinstance(auto, dict):
                continue
            commands = extract_conversation_commands(auto, blueprints_dir)
            if not commands:
                continue
            title = section_title_for(auto.get("alias"), Path(automations_file).stem)
            add(title, Path(automations_file).name, commands)

    # 3. custom sentence files (one section per file)
    if sentences_dir and Path(sentences_dir).is_dir():
        for path in sorted(Path(sentences_dir).glob("*/*.y*ml")):
            commands = extract_sentence_file_commands(load_yaml_safe(path))
            if commands:
                add(sentence_file_title(path), path.name, commands)

    result_sections = []
    for title in sorted(sections.keys()):
        bucket = sections[title]
        result_sections.append({
            "title": title,
            "source_files": sorted(bucket["source_files"]),
            "commands": sorted(bucket["commands"]),
        })
    return result_sections


def main():
    package_dir = sys.argv[1] if len(sys.argv) > 1 else "/config/packages"
    automations_file = sys.argv[2] if len(sys.argv) > 2 else "/config/automations.yaml"
    blueprints_dir = sys.argv[3] if len(sys.argv) > 3 else "/config/blueprints/automation"
    sentences_dir = sys.argv[4] if len(sys.argv) > 4 else "/config/custom_sentences"

    sections = scan(package_dir, automations_file, blueprints_dir, sentences_dir)
    output = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "sections": sections,
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()
