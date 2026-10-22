# Quadrature encoder decoder

Reads a rotary encoder (channels A and B) and keeps an 8 bit position count.

- Inputs `ui_in[0]` = A, `ui_in[1]` = B are asynchronous, so each passes through a two flop synchronizer before use.
- The decoder compares the synchronized state with the state it saw one clock earlier. With state = (B << 1) | A, the forward
  Gray sequence is 0 -> 1 -> 3 -> 2 -> 0. One step forward adds 1 to the count, one step backward subtracts 1 (8 bit wrap).
  No change does nothing. A jump of two steps (both channels changed at once) is illegal: the count is unchanged and the
  sticky error flag is set.
- `uio_in[0]` = CLEAR: while high at a rising edge, count and error flag are cleared (this takes priority over counting).
- `uo_out` = count. `uio_out[7]` = error flag, the only `uio` output (`uio_oe` = 0x80).
- Reset clears the synchronizers, the previous state, count and error flag.
