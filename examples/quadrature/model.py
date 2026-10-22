"""Cycle-level reference model: quadrature decoder with a two flop synchronizer."""
CYCLES = 4000
ORDER = [0, 1, 3, 2]   # forward Gray sequence of (B << 1) | A


class Model:
    def reset(self):
        self.sync1 = self.sync2 = self.prev = 0
        self.count = 0
        self.error = 0

    def cycle(self, ui_in, uio_in):
        outputs = (self.count, self.error << 7, 0x80)
        step = (ORDER.index(self.sync2) - ORDER.index(self.prev)) % 4
        if uio_in & 1:
            self.count, self.error = 0, 0
        elif step == 1:
            self.count = (self.count + 1) & 0xFF
        elif step == 3:
            self.count = (self.count - 1) & 0xFF
        elif step == 2:
            self.error = 1
        self.prev, self.sync2, self.sync1 = self.sync2, self.sync1, ui_in & 3
        return outputs


def stimulus(rng, cycles):
    position, hold = 0, 0
    for i in range(cycles):
        if hold == 0:
            r = rng.random()
            if r < 0.02:
                position = (position + 2) % 4          # illegal jump
            elif r < 0.6:
                position = (position + rng.choice([1, 1, 1, -1])) % 4
            hold = rng.choice([1, 1, 2, 3, 5])
        hold -= 1
        clear = 1 if rng.random() < 0.01 else 0
        reset = 0 if i == cycles // 2 else 1
        yield ORDER[position] | (rng.randrange(64) << 2), clear | (rng.randrange(128) << 1), reset
