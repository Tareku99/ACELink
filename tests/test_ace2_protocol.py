import unittest

from ace2_protocol import (
    END_MARKER,
    PREAMBLE,
    build_packet,
    crc16_kermit,
    parse_packet,
    pb_decode,
    pb_uint32,
)


class ACE2ProtocolTests(unittest.TestCase):
    def test_crc16_kermit_known_packet_inner(self):
        inner = bytes.fromhex("0001000000")
        self.assertEqual(crc16_kermit(inner), 0x2C33)

    def test_build_packet_shape(self):
        packet = build_packet(0, seq=1)
        self.assertTrue(packet.startswith(PREAMBLE))
        self.assertEqual(packet[-1], END_MARKER)
        self.assertEqual(packet.hex(), "ffaa0001000000332cfe")

    def test_parse_valid_packet(self):
        packet = bytearray(build_packet(7, b"\x08\x01", seq=3, flags=0x80))
        frame, consumed = parse_packet(packet)
        self.assertEqual(consumed, len(packet))
        self.assertIsNotNone(frame)
        self.assertEqual(frame.cmd, 7)
        self.assertEqual(frame.seq, 3)
        self.assertTrue(frame.is_response)
        self.assertEqual(frame.payload, b"\x08\x01")

    def test_parse_rejects_bad_crc(self):
        packet = bytearray(build_packet(0, seq=1))
        packet[-3] ^= 0xFF
        frame, consumed = parse_packet(packet)
        self.assertIsNone(frame)
        self.assertEqual(consumed, len(packet))

    def test_parse_skips_noise(self):
        packet = bytearray(b"\x00\x01" + build_packet(0, seq=1))
        frame, consumed = parse_packet(packet)
        self.assertIsNone(frame)
        self.assertEqual(consumed, 2)
        del packet[:consumed]
        frame, consumed = parse_packet(packet)
        self.assertIsNotNone(frame)
        self.assertEqual(frame.cmd, 0)

    def test_pb_uint32_round_trip(self):
        payload = pb_uint32(1, 300) + pb_uint32(4, 1)
        fields = pb_decode(payload)
        self.assertEqual(fields[1][0][1], 300)
        self.assertEqual(fields[4][0][1], 1)


if __name__ == "__main__":
    unittest.main()
