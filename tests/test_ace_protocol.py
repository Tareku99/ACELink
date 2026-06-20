import unittest

from ace_protocol import END_MARKER, PREAMBLE, build_request, parse_response


class ACEProProtocolTests(unittest.TestCase):
    def test_build_request_shape(self):
        packet = build_request("get_info", 1)
        self.assertTrue(packet.startswith(PREAMBLE))
        self.assertEqual(packet[-1], END_MARKER)
        self.assertIn(b'"method": "get_info"', packet)

    def test_parse_valid_response(self):
        payload = b'{"id": 1, "result": {"version": "1.0"}}'
        from ace_protocol import _calc_crc
        import struct

        frame = bytearray(
            PREAMBLE
            + struct.pack("<H", len(payload))
            + payload
            + struct.pack("<H", _calc_crc(payload))
            + bytes([END_MARKER])
        )
        expected_len = len(frame)
        response, consumed = parse_response(frame)
        self.assertEqual(consumed, expected_len)
        self.assertEqual(response["result"]["version"], "1.0")

    def test_parse_rejects_bad_crc(self):
        packet = bytearray(build_request("get_status", 2))
        packet[-3] ^= 0xFF
        response, consumed = parse_response(packet)
        self.assertIsNone(response)
        self.assertEqual(consumed, 0)


if __name__ == "__main__":
    unittest.main()
