# Chip Order

**Describe the chip in Python. Get back a tapeout ready Tiny Tapeout repo.** → https://joonsense.github.io/chip-order/

You write `spec.md` (pins and protocol) and `model.py` (a cycle-level Python model). An AI agent writes the Verilog.
It is delivered only after it

1. passes Verilator `-Wall` lint,
2. matches your model on every output pin, every clock, over three seeds with a reset mid run (cocotb + Icarus),
3. matches it again as a Yosys gate netlist,
4. catches injected faults (mutation test of the test itself),
5. fits the tile and 50 MHz by a sky130 model calibrated on 11 real layouts,
6. passes the Tiny Tapeout gds, precheck and gate level workflows in GitHub Actions.

## Order

[Open an order issue](https://github.com/Joonsense/chip-order/issues/new?template=order.yml), or run your model on the
[page](https://joonsense.github.io/chip-order/#try) and press *Order this design*. Pilot: the first 10 orders are free.

## Model contract

```python
class Model:
    def reset(self): ...
    def cycle(self, ui_in, uio_in):      # inputs of this clock
        return uo_out, uio_out, uio_oe   # outputs just before the next rising edge, then advance one clock

def stimulus(rng, cycles):               # optional: drive your protocol instead of random bytes
    yield ui_in, uio_in                  # or (ui_in, uio_in, rst_n)
```

## Delivered

| Order | RTL | Repository |
|---|---|---|
| 4 channel PWM | hand written, verified by the flow | [tt-order-pwm4](https://github.com/Joonsense/tt-order-pwm4) |
| Quadrature encoder decoder | agent, first attempt, 53 s | [tt-order-quadrature](https://github.com/Joonsense/tt-order-quadrature) |

Page source: `index.html` (static, Pyodide runs the model in the browser). Apache 2.0.
