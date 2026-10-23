#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Instant order check, run by .github/workflows/order-check.yml on every order issue.

Reads the issue from the GitHub event file, checks model.py against the contract over the same seeds and cycles the
delivered cocotb test uses, and, if the order includes Verilog, runs lint plus the cycle exact cocotb test on the RTL and
on a Yosys netlist. The check job has no token (the issue content is untrusted code) and writes only JSON; the comment
job renders that JSON with --render from the trusted checkout, validating every field.

  check_order.py EVENT_JSON RESULT_JSON
  check_order.py --render RESULT_JSON COMMENT_MD
  check_order.py --needs-tools EVENT_JSON
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
          'Your own Verilog (optional)': 'rtl', 'Pin names (optional)': 'pins', 'Anything else': 'notes'}
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


def check_rtl(work: Path, rtl: str, top: str) -> dict:
    """Structured result only: the comment job renders it, so nothing here can inject Markdown."""
    if re.search(r'`include\b', rtl):
        return {'status': 'rejected', 'reason': 'include'}
    (work / 'src').mkdir()
    (work / 'src' / 'project.v').write_text(rtl.rstrip() + '\n')
    code, text = run(['iverilog', '-E', '-o', 'pre.v', 'src/project.v'], work, 60)
    if code != 0:
        return {'status': 'rejected', 'reason': 'preprocessor', 'detail': tail(text)}
    bad = sorted({t for t in re.findall(r'\$[A-Za-z_][\w$]*', (work / 'pre.v').read_text()) if t not in ALLOWED_TASKS})
    if bad:
        return {'status': 'rejected', 'reason': 'system_tasks', 'detail': ' '.join(bad)}
    code, text = run(['verilator', '--lint-only', '-Wall', '-Wno-DECLFILENAME', '-Wno-UNUSEDSIGNAL', '--top-module', top,
                      'src/project.v'], work, 120)
    errors = [l for l in text.splitlines() if l.startswith('%Error') and 'Exiting due to' not in l]
    warnings = [l for l in text.splitlines() if l.startswith('%Warning')]
    result = {'status': 'fail', 'lint_errors': len(errors), 'lint_warnings': len(warnings), 'sims': []}
    if errors:
        result['detail'] = '\n'.join(errors[:10])
        return result
    test = work / 'test'
    test.mkdir()
    for name in ('test.py', 'Makefile'):
        shutil.copy(KIT / name, test / name)
    (test / 'tb.v').write_text((KIT / 'tb.v').read_text().replace('__TOP__', top))
    shutil.copy(work / 'model.py', test / 'model.py')
    for stage, gates in (('rtl', ''), ('netlist', 'synth')):
        if gates:
            code, text = run(['yosys', '-q', '-p', f'read_verilog -sv src/project.v; synth -flatten -top {top}; opt_clean; '
                              'write_verilog -noattr test/synth.v'], work, 600)
            if code != 0:
                result['sims'].append({'stage': stage, 'status': 'synthesis_failed', 'detail': tail(text)})
                return result
        report = test / 'mismatch.json'
        code, text = run(['env', f'PWD={test}', f'ORDER_REPORT={report}', 'make', '-s'] + ([f'GATES={gates}'] if gates else []), test, 900)
        matched = re.findall(r'(\d+) cycles matched the model', text)
        if code == 0 and matched:
            result['sims'].append({'stage': stage, 'status': 'pass', 'cycles': int(matched[-1])})
            continue
        if report.is_file():
            m = json.loads(report.read_text())
            result['sims'].append({'stage': stage, 'status': 'mismatch', 'seed': m['seed'], 'cycle': m['cycle'],
                                   'ui_in': m['ui_in'], 'uio_in': m['uio_in'], 'expected': m['expected'], 'got': m['got']})
        else:
            result['sims'].append({'stage': stage, 'status': 'did_not_run', 'detail': tail(text)})
        return result
    result['status'] = 'pass'
    return result


def check(event_path: str) -> dict:
    fields = parse(json.loads(Path(event_path).read_text()).get('issue', {}).get('body', ''))
    data = {'name': slug(fields.get('name')), 'model': {'status': 'missing'}, 'rtl': None}
    if not fields.get('model'):
        return data
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
            data['model'] = {'status': 'fail', 'detail': stats['error'] if stats else tail(text, 6)}
            return data
        data['model'] = {'status': 'pass', **stats}
        if fields.get('rtl', '').strip():
            data['rtl'] = check_rtl(work, fields['rtl'], f"tt_um_joonsense_{data['name']}")
    return data


# --- rendering: runs in the trusted comment job, from main, on the untrusted JSON above ---------------------------

def _int(value, low=0, high=10 ** 9) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise ValueError('bad number')
    return value


def _code(text) -> str:
    """Free text only ever appears inside a fenced block, without backticks, capped."""
    clean = str(text).replace('`', "'")[:1500]
    return '```text\n' + clean + '\n```'


def render(data: dict) -> str:
    name = data.get('name', '')
    if not isinstance(name, str) or not re.fullmatch(r'[a-z0-9_]{1,24}', name):
        name = 'design'
    lines = [f'## Instant check: `tt_um_joonsense_{name}`', '']
    model = data.get('model') or {}
    status = model.get('status')
    if status == 'missing':
        lines.append('No `model.py` found in this issue. Use the order form, or run your model on the chip-order page '
                     'and press *Order this design*.')
    elif status == 'fail':
        lines += ['**Model: FAIL.** The contract check did not pass, so no Verilog can be checked against it yet.', '',
                  _code(model.get('detail', '')), '', 'Edit the issue to fix it; this check runs again on every edit.']
    elif status == 'pass':
        toggles = model.get('uo_toggles') or []
        used = [f'uo_out[{b}]' for b in range(8) if b < len(toggles) and _int(toggles[b])]
        oe = ', '.join(f'0x{_int(v, 0, 255):02x}' for v in (model.get('uio_oe_values') or [])[:4])
        lines += [f"**Model: pass.** {_int(model.get('cycles')):,} cycles over seeds {', '.join(map(str, SEEDS))} "
                  f"({_int(model.get('cycles_per_seed')):,} per seed, {_int(model.get('resets')):,} reset cycles).", '',
                  '| Coverage hint | Value |', '|---|---|',
                  f"| Stimulus | {'your stimulus()' if model.get('custom_stimulus') is True else 'random bytes (add stimulus() to drive your protocol)'} |",
                  f"| Output bits that toggle | {', '.join(used) if used else 'none: the outputs never change, so the test proves little'} |",
                  f"| Distinct uo_out values | {_int(model.get('uo_values'), 0, 256)} |",
                  f"| uio_oe values | {oe or '0x00'} |"]
        if _int(model.get('resets')) == 0:
            lines.append('| Reset mid run | none: consider yielding (ui_in, uio_in, 0) once to test reset |')
        rtl = data.get('rtl')
        if isinstance(rtl, dict):
            lines += ['', '### Your Verilog', '']
            reasons = {'include': '`include is not allowed.', 'preprocessor': 'the preprocessor failed.',
                       'system_tasks': 'only $signed, $unsigned, $clog2 and $bits are allowed.'}
            if rtl.get('status') == 'rejected':
                lines.append(f"**Rejected:** {reasons.get(rtl.get('reason'), 'not accepted.')}")
                if rtl.get('detail'):
                    lines += ['', _code(rtl['detail'])]
            else:
                lines += ['| Check | Result |', '|---|---|',
                          f"| Verilator -Wall | {'FAIL' if _int(rtl.get('lint_errors')) else 'pass'}, {_int(rtl.get('lint_warnings'))} warnings |"]
                labels = {'rtl': 'RTL vs your model', 'netlist': 'Yosys netlist vs your model'}
                details = []
                for sim in (rtl.get('sims') or [])[:2]:
                    label = labels.get(sim.get('stage'), 'Simulation')
                    if sim.get('status') == 'pass':
                        lines.append(f"| {label} | pass, {_int(sim.get('cycles')):,} cycles bit exact |")
                    elif sim.get('status') == 'mismatch':
                        lines.append(f"| {label} | FAIL at seed {_int(sim.get('seed'))} cycle {_int(sim.get('cycle'))} |")
                        exp = [_int(v, 0, 255) if v is not None else None for v in (sim.get('expected') or [])[:3]]
                        got = [_int(v, 0, 255) if v is not None else None for v in (sim.get('got') or [])[:3]]
                        details.append(_code(f"{label}\ninputs ui_in=0x{_int(sim.get('ui_in'), 0, 255):02x} "
                                             f"uio_in=0x{_int(sim.get('uio_in'), 0, 255):02x}\n"
                                             f"expected (uo_out, uio_out&oe, uio_oe) = {exp}\ngot                                 = {got}"))
                    else:
                        lines.append(f"| {label} | FAIL ({'synthesis failed' if sim.get('status') == 'synthesis_failed' else 'did not compile or run'}) |")
                        details.append(_code(sim.get('detail', '')))
                if rtl.get('detail'):
                    details.append(_code(rtl['detail']))
                for block in details:
                    lines += ['', block]
        else:
            lines += ['', 'Next: the agent writes the Verilog and the full flow runs (lint, RTL and netlist against this model, '
                      'mutation test, sky130 fit, Tiny Tapeout layout). The result is posted here.']
    lines += ['', '<sub>Automatic check by chip-order. The order code runs in a job without any token or secret.</sub>']
    return '\n'.join(lines) + '\n'


def needs_tools(event_path: str) -> bool:
    body = json.loads(Path(event_path).read_text()).get('issue', {}).get('body', '')
    return bool(parse(body).get('rtl', '').strip())


if __name__ == '__main__':
    if sys.argv[1] == '--needs-tools':
        print('yes' if needs_tools(sys.argv[2]) else 'no')
    elif sys.argv[1] == '--render':
        try:
            body = render(json.loads(Path(sys.argv[2]).read_text()))
        except (ValueError, TypeError, AttributeError, json.JSONDecodeError):
            body = '## Instant check\n\nThe check produced a result that could not be read. The maintainer will look at it.\n'
        Path(sys.argv[3]).write_text(body)
    else:
        Path(sys.argv[2]).write_text(json.dumps(check(sys.argv[1])))
