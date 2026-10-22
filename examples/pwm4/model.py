"""Cycle-level reference model: 4 channel PWM controller."""
CYCLES = 3000


class Model:
    def reset(self):
        self.counter = 0
        self.duty = [0, 0, 0, 0]

    def cycle(self, ui_in, uio_in):
        out = sum(1 << ch for ch in range(4) if self.counter < self.duty[ch])
        if uio_in & 1:
            self.duty[(uio_in >> 1) & 3] = ui_in
        self.counter = (self.counter + 1) & 0xFF
        return out, 0, 0


def stimulus(rng, cycles):
    for i in range(cycles):
        write = rng.random() < 0.05
        ui = rng.choice([0, 1, 254, 255, rng.randrange(256)])
        uio = (rng.randrange(4) << 1) | int(write) | (rng.randrange(32) << 3)
        reset = 0 if i == cycles // 2 else 1   # one reset in the middle of the run
        yield ui, uio, reset
