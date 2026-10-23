# tiny8: an 8 bit accumulator CPU

A small CPU with 16 bytes of memory shared by program and data. Programs are loaded over the pins, then run one
instruction per clock.

Pins
- `uio_in[0]` LOAD: while high, the byte on `ui_in` is written to memory at the load pointer, and the pointer advances (wraps 15 -> 0).
- `uio_in[1]` RUN: while high (and LOAD and RESTART low), the CPU executes one instruction per clock unless halted.
- `uio_in[2]` RESTART: while high, PC, load pointer and the halted flag go to 0. Memory, accumulator and output keep their values.
  Priority when several are high: RESTART, then LOAD, then RUN.
- `uo_out` is the output register, written by OUT.
- `uio_out[7:4]` = PC, `uio_out[3]` = halted. These five are outputs (`uio_oe` = 0xF8), `uio[2:0]` are inputs.

Instructions (opcode in bits 7:4, operand k or address a in bits 3:0). Every instruction takes one clock. PC wraps at 16.
| Op | Name | Effect |
|---|---|---|
| 0 | NOP | |
| 1 | LDI k | acc = k |
| 2 | LD a | acc = mem[a] |
| 3 | ST a | mem[a] = acc (programs may modify themselves) |
| 4 | ADD a | acc = acc + mem[a] (8 bit wrap) |
| 5 | SUB a | acc = acc - mem[a] (8 bit wrap) |
| 6 | AND a | acc = acc & mem[a] |
| 7 | OR a | acc = acc \| mem[a] |
| 8 | XOR a | acc = acc ^ mem[a] |
| 9 | SHL | acc = acc << 1 (8 bit) |
| A | SHR | acc = acc >> 1 |
| B | JMP a | PC = a |
| C | JZ a | PC = a if acc == 0, else PC + 1 |
| D | JNZ a | PC = a if acc != 0, else PC + 1 |
| E | OUT | output register = acc |
| F | HLT | halted = 1, PC stays |

Reset clears memory, accumulator, output, PC, load pointer and halted.
