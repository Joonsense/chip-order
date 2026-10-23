# SPDX-License-Identifier: Apache-2.0
# Cycle-exact check against the reference model in model.py (chip-lab order flow).
# Every cycle: drive inputs after the falling edge, then compare uo_out, uio_oe and uio_out (bits with uio_oe set)
# with Model.cycle(ui_in, uio_in) before the next rising edge. Several seeds, each starting from a fresh reset.
import json
import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly

import model as reference

SEEDS = [int(s) for s in os.environ.get("ORDER_SEEDS", "42,917,2027").split(",")]
CYCLES = int(os.environ.get("ORDER_CYCLES", getattr(reference, "CYCLES", 2000)))


def default_stimulus(rng, cycles):
    for _ in range(cycles):
        yield rng.randrange(256), rng.randrange(256)


def value(signal):
    v = signal.value
    return v.to_unsigned() if v.is_resolvable else None


def hexes(t):
    return "(" + ", ".join("x" if v is None else f"0x{v:02x}" for v in t) + ")"


@cocotb.test()
async def test_cycle_exact_against_model(dut):
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    stimulus = getattr(reference, "stimulus", default_stimulus)
    checked = 0
    for seed in SEEDS:
        rng = random.Random(seed)
        model = reference.Model()
        model.reset()
        await FallingEdge(dut.clk)
        dut.ena.value = 1
        dut.ui_in.value = 0
        dut.uio_in.value = 0
        dut.rst_n.value = 0
        await ClockCycles(dut.clk, 5)
        history = []
        for step, item in enumerate(stimulus(rng, CYCLES)):
            await FallingEdge(dut.clk)
            ui, uio = item[0] & 0xFF, item[1] & 0xFF
            rst = item[2] if len(item) > 2 else 1
            dut.ui_in.value = ui
            dut.uio_in.value = uio
            dut.rst_n.value = rst
            await ReadOnly()
            if not rst:
                model.reset()
                history = history[-7:] + [{"cycle": step, "reset": True}]
                continue
            uo, uio_out, oe = (v & 0xFF for v in model.cycle(ui, uio))
            want = (uo, uio_out & oe, oe)
            got_oe = value(dut.uio_oe)
            got_uio = value(dut.uio_out)
            got = (value(dut.uo_out), None if got_uio is None or got_oe is None else got_uio & oe, got_oe)
            entry = {"cycle": step, "ui_in": ui, "uio_in": uio, "expected": list(want), "got": list(got)}
            if got != want:
                report = {"seed": seed, **entry, "history": history}
                path = os.environ.get("ORDER_REPORT")
                if path:
                    with open(path, "w") as f:
                        json.dump(report, f)
                assert False, (f"seed {seed} cycle {step}: ui_in=0x{ui:02x} uio_in=0x{uio:02x} "
                               f"expected (uo_out, uio_out&oe, uio_oe)={hexes(want)} got {hexes(got)}")
            history = history[-7:] + [entry]
            checked += 1
    dut._log.info(f"{checked} cycles matched the model over seeds {SEEDS}")
