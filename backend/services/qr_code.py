"""A QR code as rows of 0 and 1, for the page to draw. Byte mode, error correction level M, versions 1 to 10.

Pure standard library, so the secret never leaves this server for a drawing service and the page needs neither a new
package nor a browser crypto API. Follows ISO/IEC 18004; test_two_step pins the output.
"""
from __future__ import annotations

_ECC_PER_BLOCK = {1: 10, 2: 16, 3: 26, 4: 18, 5: 24, 6: 16, 7: 18, 8: 22, 9: 22, 10: 26}
_BLOCKS = {1: 1, 2: 1, 3: 1, 4: 2, 5: 2, 6: 4, 7: 4, 8: 4, 9: 5, 10: 5}
_LEVEL_M_BITS = 0
_MASKS = (
    lambda x, y: (x + y) % 2 == 0, lambda x, y: y % 2 == 0, lambda x, y: x % 3 == 0, lambda x, y: (x + y) % 3 == 0,
    lambda x, y: (x // 3 + y // 2) % 2 == 0, lambda x, y: x * y % 2 + x * y % 3 == 0,
    lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0, lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0,
)


def _gf_times(x: int, y: int) -> int:
    product = 0
    for bit in range(7, -1, -1):
        product = (product << 1) ^ ((product >> 7) * 0x11D)
        product ^= ((y >> bit) & 1) * x
    return product


def _divisor(degree: int) -> list[int]:
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for index in range(degree):
            result[index] = _gf_times(result[index], root)
            if index + 1 < degree:
                result[index] ^= result[index + 1]
        root = _gf_times(root, 2)
    return result


def _remainder(data: bytes | list[int], divisor: list[int]) -> list[int]:
    result = [0] * len(divisor)
    for byte in data:
        factor = byte ^ result.pop(0)
        result.append(0)
        for index, coefficient in enumerate(divisor):
            result[index] ^= _gf_times(coefficient, factor)
    return result


def _raw_codewords(version: int) -> int:
    modules = (16 * version + 128) * version + 64
    if version >= 2:
        aligned = version // 7 + 2
        modules -= (25 * aligned - 10) * aligned - 55
        if version >= 7:
            modules -= 36
    return modules // 8


def _data_capacity(version: int) -> int:
    return _raw_codewords(version) - _ECC_PER_BLOCK[version] * _BLOCKS[version]


def _alignment_positions(version: int) -> list[int]:
    if version == 1:
        return []
    count = version // 7 + 2
    step = (version * 8 + count * 3 + 5) // (count * 4 - 4) * 2
    positions = [version * 4 + 10 - step * index for index in range(count - 1)]
    return [6, *reversed(positions)]


def _bits(value: int, length: int) -> list[int]:
    return [(value >> index) & 1 for index in range(length - 1, -1, -1)]


def _codewords(data: bytes, version: int) -> list[int]:
    capacity = _data_capacity(version)
    bits = [0, 1, 0, 0] + _bits(len(data), 8 if version <= 9 else 16)
    for byte in data:
        bits += _bits(byte, 8)
    bits += [0] * min(4, capacity * 8 - len(bits))
    bits += [0] * (-len(bits) % 8)
    words = [sum(bit << (7 - place) for place, bit in enumerate(bits[start:start + 8]))
             for start in range(0, len(bits), 8)]
    pad = (0xEC, 0x11)
    words += [pad[index % 2] for index in range(capacity - len(words))]

    blocks_count, ecc = _BLOCKS[version], _ECC_PER_BLOCK[version]
    raw = _raw_codewords(version)
    short_count = blocks_count - raw % blocks_count
    short_length = raw // blocks_count - ecc
    divisor, blocks, eccs, start = _divisor(ecc), [], [], 0
    for index in range(blocks_count):
        length = short_length + (0 if index < short_count else 1)
        block = words[start:start + length]
        start += length
        blocks.append(block)
        eccs.append(_remainder(block, divisor))
    joined = [block[index] for index in range(short_length + 1) for block in blocks if index < len(block)]
    return joined + [word for index in range(ecc) for word in (block[index] for block in eccs)]


class _Grid:
    def __init__(self, version: int) -> None:
        self.size = version * 4 + 17
        self.dark = [[False] * self.size for _ in range(self.size)]
        self.fixed = [[False] * self.size for _ in range(self.size)]
        self.version = version
        self._draw_fixed()

    def set(self, x: int, y: int, dark: bool) -> None:
        self.dark[y][x] = dark
        self.fixed[y][x] = True

    def _finder(self, cx: int, cy: int) -> None:
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < self.size and 0 <= y < self.size:
                    self.set(x, y, max(abs(dx), abs(dy)) not in (2, 4))

    def _draw_fixed(self) -> None:
        for index in range(self.size):
            self.set(6, index, index % 2 == 0)
            self.set(index, 6, index % 2 == 0)
        self._finder(3, 3)
        self._finder(self.size - 4, 3)
        self._finder(3, self.size - 4)
        positions = _alignment_positions(self.version)
        last = len(positions) - 1
        for i, cx in enumerate(positions):
            for j, cy in enumerate(positions):
                if (i, j) in ((0, 0), (0, last), (last, 0)):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self.set(cx + dx, cy + dy, max(abs(dx), abs(dy)) != 1)
        self.draw_format(0)
        if self.version >= 7:
            remainder = self.version
            for _ in range(12):
                remainder = (remainder << 1) ^ ((remainder >> 11) * 0x1F25)
            bits = self.version << 12 | remainder
            for index in range(18):
                dark = bool((bits >> index) & 1)
                a, b = self.size - 11 + index % 3, index // 3
                self.set(a, b, dark)
                self.set(b, a, dark)

    def draw_format(self, mask: int) -> None:
        data = _LEVEL_M_BITS << 3 | mask
        remainder = data
        for _ in range(10):
            remainder = (remainder << 1) ^ ((remainder >> 9) * 0x537)
        bits = (data << 10 | remainder) ^ 0x5412
        bit = lambda index: bool((bits >> index) & 1)  # noqa: E731
        for index in range(6):
            self.set(8, index, bit(index))
        self.set(8, 7, bit(6))
        self.set(8, 8, bit(7))
        self.set(7, 8, bit(8))
        for index in range(9, 15):
            self.set(14 - index, 8, bit(index))
        for index in range(8):
            self.set(self.size - 1 - index, 8, bit(index))
        for index in range(8, 15):
            self.set(8, self.size - 15 + index, bit(index))
        self.set(8, self.size - 8, True)

    def place(self, words: list[int]) -> None:
        position, total = 0, len(words) * 8
        right = self.size - 1
        while right >= 1:
            if right == 6:
                right = 5
            for vertical in range(self.size):
                for offset in range(2):
                    x = right - offset
                    upward = (right + 1) & 2 == 0
                    y = self.size - 1 - vertical if upward else vertical
                    if not self.fixed[y][x] and position < total:
                        self.dark[y][x] = bool((words[position >> 3] >> (7 - (position & 7))) & 1)
                        position += 1
            right -= 2

    def apply_mask(self, mask: int) -> None:
        test = _MASKS[mask]
        for y in range(self.size):
            for x in range(self.size):
                if not self.fixed[y][x] and test(x, y):
                    self.dark[y][x] = not self.dark[y][x]

    def penalty(self) -> int:
        """The four penalties of ISO/IEC 18004 7.8.3.2."""
        size, score = self.size, 0
        lines = self.dark + [[self.dark[y][x] for y in range(size)] for x in range(size)]
        finder = ((True, False, True, True, True, False, True, False, False, False, False),
                  (False, False, False, False, True, False, True, True, True, False, True))
        for line in lines:
            run, colour = 0, None
            for cell in line:
                if cell == colour:
                    run += 1
                else:
                    if run >= 5:
                        score += run - 2
                    run, colour = 1, cell
            if run >= 5:
                score += run - 2
            for start in range(size - 10):
                if tuple(line[start:start + 11]) in finder:
                    score += 40
        for y in range(size - 1):
            for x in range(size - 1):
                if self.dark[y][x] == self.dark[y][x + 1] == self.dark[y + 1][x] == self.dark[y + 1][x + 1]:
                    score += 3
        dark = sum(sum(row) for row in self.dark)
        score += abs(dark * 20 - size * size * 10) // (size * size) * 10
        return score


def encode(text: str, mask: int | None = None) -> list[str]:
    """Rows of "0" and "1", dark being 1. Raises ValueError when the text will not fit version 10. The mask is
    chosen by penalty score unless given; any of the eight reads the same."""
    data = text.encode("utf-8")
    for version in _ECC_PER_BLOCK:
        if len(data) + 2 + (0 if version <= 9 else 1) <= _data_capacity(version):
            break
    else:
        raise ValueError("Too long for this QR code")
    words = _codewords(data, version)
    grid = _Grid(version)
    grid.place(words)
    best, best_score = mask or 0, None
    for candidate in range(8) if mask is None else ():
        grid.apply_mask(candidate)
        grid.draw_format(candidate)
        score = grid.penalty()
        if best_score is None or score < best_score:
            best, best_score = candidate, score
        grid.apply_mask(candidate)
    grid.apply_mask(best)
    grid.draw_format(best)
    return ["".join("1" if cell else "0" for cell in row) for row in grid.dark]
