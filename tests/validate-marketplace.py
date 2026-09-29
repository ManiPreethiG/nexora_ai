#!/usr/bin/env python3
"""Structural validation of the marketplace: manifest, skill folders, frontmatter.

Mirrors what `skills-ref validate` checks per skill, plus this contest's
manifest convention, without requiring the tool to be installed.

Usage: python3 tests/validate-marketplace.py
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME_RX = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
errors, warnings = [], []


def parse_frontmatter(path):
    """Minimal YAML frontmatter reader: scalars, folded scalars, flat lists."""
    with open(path) as fh:
        text = fh.read()
    if not text.startswith("---"):
        return None, "no YAML frontmatter"
    end = text.find("\n---", 3)
    if end == -1:
        return None, "unterminated frontmatter"
    block, data, key = text[3:end], {}, None
    for line in block.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^(\w[\w-]*):\s*(.*)$", line)
        if m and not line.startswith((" ", "\t")):
            key, value = m.group(1), m.group(2).strip()
            data[key] = "" if value in (">-", ">", "|", "|-", "") else value
        elif key and line.startswith((" ", "\t")):
            data[key] = (str(data.get(key, "")) + " " + line.strip()).strip()
    return data, None


def check_skill(skill_id, path):
    folder = os.path.join(ROOT, path)
    if not os.path.isdir(folder):
        errors.append("%s: folder %s does not exist" % (skill_id, path))
        return
    md = os.path.join(folder, "SKILL.md")
    if not os.path.exists(md):
        errors.append("%s: no SKILL.md" % skill_id)
        return
    fm, err = parse_frontmatter(md)
    if err:
        errors.append("%s: %s" % (skill_id, err))
        return
    for field in ("name", "description"):
        if not fm.get(field):
            errors.append("%s: frontmatter missing required field '%s'" % (skill_id, field))
    name = fm.get("name", "")
    if name and not NAME_RX.match(name):
        errors.append("%s: name %r is not lowercase-hyphen" % (skill_id, name))
    if name and name != os.path.basename(path):
        errors.append("%s: frontmatter name %r != folder %r"
                      % (skill_id, name, os.path.basename(path)))
    if name != skill_id:
        errors.append("%s: manifest id != frontmatter name %r" % (skill_id, name))
    desc = fm.get("description", "")
    if len(desc) < 60:
        warnings.append("%s: description is short (%d chars); it is what selects the skill"
                        % (skill_id, len(desc)))
    if len(desc) > 1400:
        warnings.append("%s: description is %d chars; consider trimming" % (skill_id, len(desc)))
    if not fm.get("license"):
        warnings.append("%s: no license in frontmatter" % skill_id)
    body = open(md).read().split("\n---", 1)[-1]
    if len(body.split()) < 80:
        warnings.append("%s: SKILL.md body is very short" % skill_id)
    for script in [f for f in os.listdir(os.path.join(folder, "scripts"))
                   if f.endswith(".py")] if os.path.isdir(os.path.join(folder, "scripts")) else []:
        p = os.path.join(folder, "scripts", script)
        try:
            compile(open(p).read(), p, "exec")
        except SyntaxError as e:
            errors.append("%s: %s does not compile: %s" % (skill_id, script, e))


def main():
    manifest_path = os.path.join(ROOT, "marketplace.json")
    if not os.path.exists(manifest_path):
        print("FAIL: no marketplace.json at the root")
        return 1
    try:
        m = json.load(open(manifest_path))
    except json.JSONDecodeError as e:
        print("FAIL: marketplace.json is not valid JSON: %s" % e)
        return 1

    for field in ("name", "version", "skills"):
        if field not in m:
            errors.append("marketplace.json missing '%s'" % field)
    skills = m.get("skills", [])
    entries = [s for s in skills if s.get("entrypoint")]
    if len(entries) != 1:
        errors.append("expected exactly one entrypoint skill, found %d" % len(entries))
    ids = [s.get("id") for s in skills]
    if len(ids) != len(set(ids)):
        errors.append("duplicate skill ids in the manifest")
    for s in skills:
        if not s.get("id") or not s.get("path"):
            errors.append("manifest entry missing id or path: %r" % s)
            continue
        check_skill(s["id"], s["path"])

    listed = {s.get("path") for s in skills}
    for d in sorted(os.listdir(os.path.join(ROOT, "skills"))):
        p = "skills/" + d
        if os.path.isdir(os.path.join(ROOT, p)) and p not in listed:
            errors.append("skill folder %s exists but is not listed in the manifest" % p)

    schema = os.path.join(ROOT, "skills/audit-orchestrator/references/report-schema.json")
    if os.path.exists(schema):
        try:
            json.load(open(schema))
        except json.JSONDecodeError as e:
            errors.append("report-schema.json is not valid JSON: %s" % e)
    else:
        errors.append("report-schema.json is missing")

    for w in warnings:
        print("WARN  " + w)
    for e in errors:
        print("ERROR " + e)
    print("\n%d skills checked · %d errors · %d warnings" % (len(skills), len(errors), len(warnings)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
