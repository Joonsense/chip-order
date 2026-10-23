"""Cycle-level reference model: tiny8 accumulator CPU."""
CYCLES = 4000
FIB = [0x10, 0x3E, 0x11, 0x3F, 0x2E, 0xE0, 0x4F, 0x3D, 0x2F, 0x3E, 0x2D, 0x3F, 0xB4, 0x00, 0x00, 0x00]
COUNTDOWN = [0x29, 0xE0, 0x5A, 0xD1, 0xE0, 0xF0, 0x00, 0x00, 0x00, 0xFF, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00]
COUNTER = [0x2D, 0x4E, 0x3D, 0x2D, 0xE0, 0xB0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x13, 0x01, 0x00]
# rewrites its own instruction at address 0 (LDI k) with k + 1, so the program it runs changes every pass
SELFMOD = [0x10, 0xE0, 0x20, 0x4F, 0x30, 0xB0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01]


class Model:
    def reset(self):
        self.mem = [0] * 16
        self.acc = self.out = self.pc = self.ptr = self.halted = 0

    def cycle(self, ui_in, uio_in):
        outputs = (self.out, (self.pc << 4) | (self.halted << 3), 0xF8)
        if uio_in & 4:
            self.pc = self.ptr = self.halted = 0
        elif uio_in & 1:
            self.mem[self.ptr] = ui_in
            self.ptr = (self.ptr + 1) & 15
        elif uio_in & 2 and not self.halted:
            self.execute()
        return outputs

    def execute(self):
        ins = self.mem[self.pc]
        op, a = ins >> 4, ins & 15
        nxt = (self.pc + 1) & 15
        m = self.mem[a]
        if op == 1: self.acc = a
        elif op == 2: self.acc = m
        elif op == 3: self.mem[a] = self.acc
        elif op == 4: self.acc = (self.acc + m) & 0xFF
        elif op == 5: self.acc = (self.acc - m) & 0xFF
        elif op == 6: self.acc &= m
        elif op == 7: self.acc |= m
        elif op == 8: self.acc ^= m
        elif op == 9: self.acc = (self.acc << 1) & 0xFF
        elif op == 10: self.acc >>= 1
        elif op == 11: nxt = a
        elif op == 12 and self.acc == 0: nxt = a
        elif op == 13 and self.acc != 0: nxt = a
        elif op == 14: self.out = self.acc
        elif op == 15:
            self.halted = 1
            nxt = self.pc
        self.pc = nxt


def stimulus(rng, cycles):
    """Load a program (three real ones or random bytes), run it with pauses, sometimes restart mid run."""
    i = 0
    while i < cycles:
        program = rng.choice([FIB, COUNTDOWN, COUNTER, SELFMOD, [rng.randrange(256) for _ in range(16)]])
        yield 0, 4                                    # RESTART: pointer and PC to 0
        i += 1
        for byte in program:
            yield byte, 1 | (rng.randrange(32) << 3)  # LOAD, upper uio bits are noise
            i += 1
        for _ in range(rng.randrange(40, 200)):
            if i >= cycles:
                return
            r = rng.random()
            uio = 2 if r < 0.85 else (0 if r < 0.97 else 6)   # run, pause, or RUN with RESTART (restart wins)
            yield rng.randrange(256), uio | (rng.randrange(32) << 3), 0 if i == cycles // 2 else 1
            i += 1
