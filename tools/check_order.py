#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Instant order check, run by .github/workflows/order-check.yml on every order issue.

Reads the issue from the GitHub event file, checks model.py against the contract over the same seeds and cycles the
delivered cocotb test uses, and, if the order includes Verilog, runs lint plus the cycle exact cocotb test on the RTL and
on a Yosys netlist. Writes a Markdown report. This job has no token: the issue content is untrusted code.

  check_order.py EVENT_JSON REPORT_MD
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE / 'kit'
FIELDS = {'Design name': 'name', 'spec.md': 'spec', 'model.py': 'model', 'Largest tile size you accept': 'tiles',
          'Your own Verilog (optional)': 'rtl', 'Anything else': 'notes'}
ALLOWED_TASKS = {'$signed', '$unsigned', '$clog2', '$bits'}
SEEDS = [42, 917, 2027]

CONTRACT = r'''
import json, random, sys
sys.path.insert(0, ".")
import model as reference
cycles = int(getattr(reference, "CYCLES", 2000))
stimulus = getattr(reference, "stimulus", None)
stats = {"cycles": 0, "resets": 0, "custom_stimulus": stimulus is not None, "cycles_per_seed": cycles,
         "uo_toggles": [0] * 8, "uio_oe_values": [], "uio_out_toggles": [0] * 8, "uo_values": 0}
seen = set()
for seed in %s:
    rng = random.Random(seed)
    m = reference.Model()
    m.reset()
    items = stimulus(rng, cycles) if stimulus else ((rng.randrange(256), rng.randrange(256)) for _ in range(cycles))
    prev = None
    for i, item in enumerate(items):
        if len(item) > 2 and not item[2]:
            m.reset(); stats["resets"] += 1; prev = None; continue
        out = m.cycle(item[0] & 255, item[1] & 255)
        if not (isinstance(out, (tuple, list)) and len(out) == 3 and all(isinstance(v, int) and 0 <= v < 256 for v in out)):
            print(json.dumps({"error": f"seed {seed} cycle {i}: Model.cycle must return three ints 0..255 (uo_out, uio_out, uio_oe), got {out!r}"}))
            sys.exit(0)
        uo, uio, oe = out
        seen.add(uo)
        if oe not in stats["uio_oe_values"]:
            stats["uio_oe_values"].append(oe)
        if prev:
            for b in range(8):
                stats["uo_toggles"][b] += ((uo ^ prev[0]) >> b) & 1
                stats["uio_out_toggles"][b] += (((uio & oe) ^ (prev[1] & prev[2])) >> b) & 1
        prev = out
        stats["cycles"] += 1
stats["uo_values"] = len(seen)
print(json.dumps(stats))
''' % SEEDS


def parse(body: str) -> dict:
    found = {}
    for section in re.split(r'^### ', body or '', flags=re.M)[1:]:
        title, _, text = section.partition('\n')
        key = FIELDS.get(title.strip())
        if not key:
            continue
        text = text.strip()
        fenced = re.match(r'^```[a-z]*\n(.*?)\n?```$', text, re.S)
        if fenced:
            text = fenced.group(1)
        found[key] = '' if text == '_No response_' else text
    return found


def slug(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', (text or '').lower()).strip('_')[:24] or 'design'


def run(command, cwd, timeout):
    try:
        p = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout + p.stderr
    except subprocess.TimeoutExpired:
        return -1, f'timed out after {timeout} s'


def tail(text: str, lines: int = 12) -> str:
    return '\n'.join(text.strip().splitlines()[-lines:])[-1500:]


def check_rtl(work: Path, rtl: str, top: str) -> list[str]:
    out = ['', '### Your Verilog', '']
    if re.search(r'`include\b', rtl):
        return out + ['**Rejected:** `` `include `` is not allowed.']
    (work / 'src').mkdir()
    (work / 'src' / 'project.v').write_text(rtl.rstrip() + '\n')
    code, text = run(['iverilog', '-E', '-o', 'pre.v', 'src/project.v'], work, 60)
    if code != 0:
        return out + ['**Preprocessor failed:**', '```', tail(text), '```']
    bad = sorted({t for t in re.findall(r'\$[A-Za-z_][\w$]*', (work / 'pre.v').read_text()) if t not in ALLOWED_TASKS})
    if bad:
        return out + [f"**Rejected:** only `$signed`, `$unsigned`, `$clog2`, `$bits` are allowed, found {', '.join(f'`{b}`' for b in bad)}."]
    rows = ['| Check | Result |', '|---|---|']
    code, text = run(['verilator', '--lint-only', '-Wall', '-Wno-DECLFILENAME', '-Wno-UNUSEDSIGNAL', '--top-module', top,
                      'src/project.v'], work, 120)
    errors = [l for l in text.splitlines() if l.startswith('%Error') and 'Exiting due to' not in l]
    warnings = [l for l in text.splitlines() if l.startswith('%Warning')]
    rows.append(f"| Verilator -Wall | {'FAIL' if errors else 'pass'}, {len(warnings)} warnings |")
    if errors:
        return out + rows + ['', '```', '\n'.join(errors[:10]), '```']
    test = work / 'test'
    test.mkdir()
    for name in ('test.py', 'Makefile'):
        shutil.copy(KIT / name, test / name)
    (test / 'tb.v').write_text((KIT / 'tb.v').read_text().replace('__TOP__', top))
    shutil.copy(work / 'model.py', test / 'model.py')
    results = {}
    for label, gates in (('RTL vs your model', ''), ('Yosys netlist vs your model', 'synth')):
        if gates:
            code, text = run(['yosys', '-q', '-p', f'read_verilog -sv src/project.v; synth -flatten -top {top}; opt_clean; '
                              'write_verilog -noattr test/synth.v'], work, 600)
            if code != 0:
                rows.append(f'| {label} | Yosys synthesis failed |')
                results[label] = tail(text)
                break
        report = test / 'mismatch.json'
        env_cmd = ['env', f'PWD={test}', f'ORDER_REPORT={report}', 'make', '-s'] + ([f'GATES={gates}'] if gates else [])
        code, text = run(env_cmd, test, 900)
        matched = re.findall(r'(\d+) cycles matched the model', text)
        if code == 0 and matched:
            rows.append(f'| {label} | pass, {int(matched[-1]):,} cycles bit exact |')
            continue
        if report.is_file():
            m = json.loads(report.read_text())
            rows.append(f"| {label} | FAIL at seed {m['seed']} cycle {m['cycle']} |")
            results[label] = (f"inputs ui_in=0x{m['ui_in']:02x} uio_in=0x{m['uio_in']:02x}\n"
                              f"expected (uo_out, uio_out&oe, uio_oe) = {m['expected']}\ngot                                 = {m['got']}\n"
                              f"previous cycles: {json.dumps(m.get('history', [])[-4:])}")
        else:
            rows.append(f'| {label} | FAIL (did not compile or run) |')
            results[label] = tail(text)
        break
    out += rows
    for label, text in results.items():
        out += ['', f'<details open><summary>{label}</summary>', '', '```', text, '```', '', '</details>']
    return out


def main(event_path: str, report_path: str) -> int:
    event = json.loads(Path(event_path).read_text())
    issue = event.get('issue', {})
    fields = parse(issue.get('body', ''))
    name = slug(fields.get('name'))
    top = f'tt_um_joonsense_{name}'
    lines = [f'## Instant check: `{top}`', '']
    if not fields.get('model'):
        lines.append('No `model.py` found in this issue. Use the order form, or run your model at '
                     'https://joonsense.github.io/chip-order/#try and press *Order this design*.')
        Path(report_path).write_text('\n'.join(lines) + '\n')
        return 0
    with tempfile.TemporaryDirectory(prefix='order-check-') as directory:
        work = Path(directory)
        (work / 'model.py').write_text(fields['model'].rstrip() + '\n')
        code, text = run([sys.executable, '-I', '-c', CONTRACT], work, 120)
        stats = None
        if code == 0:
            try:
                stats = json.loads(text.strip().splitlines()[-1])
            except (json.JSONDecodeError, IndexError):
                stats = None
        if not stats or 'error' in stats:
            detail = stats['error'] if stats else tail(text, 6)
            lines += ['**Model: FAIL.** The contract check did not pass, so no Verilog can be checked against it yet.', '',
                      '```', detail, '```', '', 'Edit the issue to fix it; this check runs again on every edit.']
            Path(report_path).write_text('\n'.join(lines) + '\n')
            return 0
        used = [f'uo_out[{b}]' for b in range(8) if stats['uo_toggles'][b]]
        oe = ', '.join(f'0x{v:02x}' for v in stats['uio_oe_values'][:4])
        lines += [f"**Model: pass.** {stats['cycles']:,} cycles over seeds {', '.join(map(str, SEEDS))} "
                  f"({stats['cycles_per_seed']:,} per seed, {stats['resets']} reset cycles).", '',
                  '| Coverage hint | Value |', '|---|---|',
                  f"| Stimulus | {'your stimulus()' if stats['custom_stimulus'] else 'random bytes (add stimulus() to drive your protocol)'} |",
                  f"| Output bits that toggle | {', '.join(used) if used else 'none: the outputs never change, so the test proves little'} |",
                  f"| Distinct uo_out values | {stats['uo_values']} |",
                  f"| uio_oe values | {oe or '0x00'} |"]
        if stats['resets'] == 0:
            lines.append('| Reset mid run | none: consider yielding `(ui_in, uio_in, 0)` once to test reset |')
        if fields.get('rtl', '').strip():
            lines += check_rtl(work, fields['rtl'], top)
        else:
            lines += ['', 'Next: the agent writes the Verilog and the full flow runs (lint, RTL and netlist against this model, '
                      'mutation test, sky130 fit, Tiny Tapeout layout). The result is posted here.']
    lines += ['', '<sub>Automatic check by chip-order. Runs without access to any token or secret.</sub>']
    Path(report_path).write_text('\n'.join(lines) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
