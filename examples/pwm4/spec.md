# 4 channel PWM controller

Four independent 8 bit PWM outputs sharing one free running 8 bit counter.

- A counter increments every clock and wraps 255 -> 0. Reset clears it and all duty registers.
- Write a duty value: put the value on `ui_in`, the channel number on `uio_in[2:1]`, and pulse `uio_in[0]` (WE) high for one clock.
  The new duty takes effect from the next clock.
- `uo_out[ch]` is high while `counter < duty[ch]`, so duty 0 is always low and duty 255 is high 255 of 256 clocks.
- `uo_out[7:4]` are 0. All `uio` pins are inputs (`uio_oe` = 0).
