from typing import List, Iterable

class A51:
    def __init__(self, key: str):
        if not isinstance(key, str):
            raise TypeError("Key harus berupa string")
        key_int = int.from_bytes(key.encode(), "big")
        self.key = key_int & ((1 << 64) - 1)

    def clock_r1(self, r1: int) -> int:
        fb = ((r1 >> 18) ^ (r1 >> 17) ^ (r1 >> 16) ^ (r1 >> 13)) & 1
        return ((r1 << 1) & 0x7FFFF) | fb  # 19 bit

    def clock_r2(self, r2: int) -> int:
        fb = ((r2 >> 21) ^ (r2 >> 20)) & 1
        return ((r2 << 1) & 0x3FFFFF) | fb  # 22 bit

    def clock_r3(self, r3: int) -> int:
        fb = ((r3 >> 22) ^ (r3 >> 21) ^ (r3 >> 20) ^ (r3 >> 7)) & 1
        return ((r3 << 1) & 0x7FFFFF) | fb  # 23 bit

    @staticmethod
    def maj(a, b, c):
        return (a & b) | (a & c) | (b & c)

    def init_registers(self, fn: int):
        if fn.bit_length() > 22:
            raise ValueError("Fn harus 22-bit atau kurang")

        r1 = r2 = r3 = 0

        for i in range(64):
            bit = (self.key >> i) & 1
            r1 = self.clock_r1(r1 ^ bit)
            r2 = self.clock_r2(r2 ^ bit)
            r3 = self.clock_r3(r3 ^ bit)

        for i in range(22):
            bit = (fn >> i) & 1
            r1 = self.clock_r1(r1 ^ bit)
            r2 = self.clock_r2(r2 ^ bit)
            r3 = self.clock_r3(r3 ^ bit)

        for _ in range(100):
            c1, c2, c3 = (r1 >> 8) & 1, (r2 >> 10) & 1, (r3 >> 10) & 1
            m = self.maj(c1, c2, c3)
            if c1 == m: r1 = self.clock_r1(r1)
            if c2 == m: r2 = self.clock_r2(r2)
            if c3 == m: r3 = self.clock_r3(r3)

        return r1, r2, r3

    def keystream_block(self, fn: int) -> List[int]:
        r1, r2, r3 = self.init_registers(fn)
        out = []
        for _ in range(228):
            c1, c2, c3 = (r1 >> 8) & 1, (r2 >> 10) & 1, (r3 >> 10) & 1
            m = self.maj(c1, c2, c3)
            if c1 == m: r1 = self.clock_r1(r1)
            if c2 == m: r2 = self.clock_r2(r2)
            if c3 == m: r3 = self.clock_r3(r3)
            ks_bit = (r1 ^ r2 ^ r3) & 1
            out.append(ks_bit)
        return out

    @staticmethod
    def bits_from_bytes(data: bytes) -> List[int]:
        return [(byte >> i) & 1 for byte in data for i in range(8)]

    @staticmethod
    def bytes_from_bits(bits: Iterable[int]) -> bytes:
        bits = list(bits)
        while len(bits) % 8 != 0:
            bits.append(0)
        out = bytearray()
        for i in range(0, len(bits), 8):
            val = sum((bits[i+j] & 1) << j for j in range(8))
            out.append(val)
        return bytes(out)

    def encrypt(self, plaintext: bytes) -> bytes:
        pt_bits = self.bits_from_bytes(plaintext)
        ct_bits = []
        block_idx = 1
        for i in range(0, len(pt_bits), 228):
            block = pt_bits[i:i+228]
            ks = self.keystream_block(block_idx)
            block_ct = [b ^ ks[j] for j, b in enumerate(block)]
            ct_bits.extend(block_ct)
            block_idx += 1
        return self.bytes_from_bits(ct_bits)

    def decrypt(self, ciphertext: bytes) -> bytes:
        return self.encrypt(ciphertext)


    def encrypt_file(self, input_path, output_path):
        with open(input_path, "rb") as f:
            data = f.read()
        cipher = self.encrypt(data)
        with open(output_path, "wb") as f:
            f.write(cipher)
        print(f"File terenkripsi: {output_path}")

    def decrypt_file(self, input_path, output_path):
        with open(input_path, "rb") as f:
            data = f.read()
        plain = self.decrypt(data)
        with open(output_path, "wb") as f:
            f.write(plain)
        print(f"File didekripsi: {output_path}")
