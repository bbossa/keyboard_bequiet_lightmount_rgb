"""Vendor protocol (interface 2) against captured frames. Needs neither the keyboard nor tshark."""
import struct, unittest

import fixtures
from lightmount import protocol as p

FRAMES = [m[0] for m in fixtures.load('frames-out.hex')]
LEDS = fixtures.load('leds-10-0d.hex')
MODE_RESPONSES = [m[0] for m in fixtures.load('responses-10-01.hex')]
INFO_REQUESTS = [m[0] for m in fixtures.load('requests-03.hex')]
VERSION_RESPONSES = [m[0] for m in fixtures.load('responses-03-01.hex')]
ALL_PACKETS = FRAMES + [pk for m in LEDS for pk in m] + MODE_RESPONSES + INFO_REQUESTS + VERSION_RESPONSES


def fields(raw):
    """(cmd, sub, data, seq, session) of a single-packet frame."""
    return raw[5], raw[6], raw[7:raw[0] + 1], struct.unpack('>H', raw[3:5])[0], raw[2]


def series(messages):
    """Group 10:0d messages into complete updates (consecutive seq, up to the last one)."""
    current = []
    for msg in messages:
        current.append(msg)
        if p.parse_leds(msg)[3]:
            yield current
            current = []


class Fixtures(unittest.TestCase):
    def test_present(self):
        self.assertGreater(len(FRAMES), 0)
        self.assertEqual(len(LEDS), 39)
        self.assertGreater(len(MODE_RESPONSES), 0)

    def test_64_bytes(self):
        for raw in ALL_PACKETS:
            self.assertEqual(len(raw), 64)


class Crc(unittest.TestCase):
    def test_check_value(self):
        # check value from the CRC catalogue for CRC-16/MODBUS
        self.assertEqual(p.crc16_modbus(b'123456789'), 0x4B37)

    def test_captured_packets(self):
        for raw in ALL_PACKETS:
            with self.subTest(raw=raw.hex()):
                self.assertEqual(struct.unpack('<H', raw[62:64])[0], p.crc16_modbus(raw[:62]))


class Frame(unittest.TestCase):
    def test_single_packet_frames(self):
        for raw in FRAMES:
            cmd, sub, data, seq, session = fields(raw)
            with self.subTest(cmd=f'{cmd:02x}:{sub:02x}', seq=seq):
                self.assertEqual(p.frame(cmd, sub, data, seq, session), raw)

    def test_seq_one_byte(self):
        # byte 3 is always 00 in a first fragment: seq only uses byte 4
        # (in continuation fragments, data already starts at byte 3)
        for raw in ALL_PACKETS:
            if raw[1] & 0x7f == 0:
                self.assertEqual(raw[3], 0x00)

    def test_frame_matches_single_fragment_message(self):
        # frame() (10:06) and message() (10:0d) describe the same format for a single packet
        for raw in FRAMES:
            cmd, sub, data, seq, session = fields(raw)
            self.assertEqual(p.message(cmd, sub, data, seq, session), [raw])


class Lighting(unittest.TestCase):
    def test_static_color(self):
        static = [r for r in FRAMES if r[5:7] == b'\x10\x06' and r[8] == p.EFFECT_STATIC
                  and r[12] == p.COLOR_MODE_SINGLE]
        self.assertGreater(len(static), 0)
        for raw in static:
            _, _, _, seq, session = fields(raw)
            self.assertEqual(p.static_color(raw[13:16], raw[10], seq, session), raw)

    def test_set_mode(self):
        modes = [r for r in FRAMES if r[5:7] == bytes(p.CMD_SET_MODE)]
        self.assertEqual({r[7] for r in modes}, {0x01, 0x03})
        for raw in modes:
            _, _, _, seq, session = fields(raw)
            self.assertEqual(p.frame(*p.CMD_SET_MODE, raw[7:8], seq, session), raw)

    def test_get_mode_request(self):
        requests = [r for r in FRAMES if r[5:7] == bytes(p.CMD_GET_MODE)]
        self.assertGreater(len(requests), 0)
        for raw in requests:
            _, _, _, seq, session = fields(raw)
            self.assertEqual(p.message(*p.CMD_GET_MODE, b'', seq, session), [raw])

    def test_get_mode_responses(self):
        # the reply echoes seq and cmd:sub, the mode is the first data byte
        self.assertEqual({r[7] for r in MODE_RESPONSES}, {p.MODE_CUSTOM, p.MODE_EFFECTS})
        for raw in MODE_RESPONSES:
            self.assertEqual(raw[5:7], bytes(p.CMD_GET_MODE))

    def test_mode_builders(self):
        for raw in FRAMES:
            cmd, sub, data, seq, session = fields(raw)
            if (cmd, sub) == p.CMD_GET_MODE:
                self.assertEqual(p.get_mode(seq, session), raw)
            elif (cmd, sub) == p.CMD_SET_MODE:
                self.assertEqual(p.set_mode(data[0], seq, session), raw)


class Replies(unittest.TestCase):
    def test_captured_responses(self):
        for resp in MODE_RESPONSES:
            _, _, _, seq, session = fields(resp)
            self.assertTrue(p.is_reply(resp, p.get_mode(seq, session)))
            self.assertFalse(p.is_reply(resp, p.get_mode((seq + 1) & 0xFF, session)))
            self.assertTrue(p.crc_ok(resp))
            self.assertIn(p.mode_of(resp), (p.MODE_EFFECTS, p.MODE_CUSTOM))

    def test_crc_rejects_corruption(self):
        raw = bytearray(FRAMES[0])
        raw[10] ^= 0x01
        self.assertFalse(p.crc_ok(raw))

    def test_frame_single_packet_only(self):
        p.frame(0x10, 0x06, bytes(p.FIRST_CAPACITY), 0)
        with self.assertRaises(ValueError):
            p.frame(0x10, 0x06, bytes(p.FIRST_CAPACITY + 1), 0)


class Identification(unittest.TestCase):
    def test_captured_requests(self):
        self.assertEqual({(r[5], r[6]) for r in INFO_REQUESTS}, {p.CMD_GET_VERSION, p.CMD_GET_SERIAL})
        for raw in INFO_REQUESTS:
            cmd, sub, data, seq, session = fields(raw)
            self.assertEqual(data, b'')
            self.assertEqual(p.frame(cmd, sub, b'', seq, session), raw)

    def test_web_requests(self):
        # IO Center Web sends them before 01:01, with session 00: the frames lightmount sends
        web = [r for r in INFO_REQUESTS if r[2] == p.SESSION_NONE]
        self.assertEqual({(r[5], r[6]) for r in web}, {p.CMD_GET_VERSION, p.CMD_GET_SERIAL})
        for raw in web:
            build = p.get_version if (raw[5], raw[6]) == p.CMD_GET_VERSION else p.get_serial
            self.assertEqual(build(raw[4]), raw)

    def test_version_responses(self):
        self.assertGreater(len(VERSION_RESPONSES), 0)
        for resp in VERSION_RESPONSES:
            self.assertEqual(p.version_of(resp), bytes.fromhex('0200010100000302'))

    def test_serial_of(self):
        resp = p.frame(*p.CMD_GET_SERIAL, bytes([4]) + b'AB12', 7, p.SESSION_NONE)
        self.assertEqual(p.serial_of(resp), 'AB12')


class KeyEvents(unittest.TestCase):
    # key events captured on 2026-10-15
    def event(self, data):
        return p.frame(*p.CMD_KEY_EVENT, bytes.fromhex(data), 0x00, p.SESSION)

    def test_fn_effect(self):
        self.assertEqual(p.fn_function(self.event('5c80010903')), p.FN_EFFECT)  # Fn+→

    def test_fn_alone(self):
        self.assertEqual(p.fn_function(self.event('4b80011b')), 0x1b)

    def test_plain_keys(self):
        for data in ('530001010050', '5c000101004f'):  # ←, →
            self.assertIsNone(p.fn_function(self.event(data)))

    def test_other_messages(self):
        self.assertIsNone(p.fn_function(p.get_mode(1)))
        self.assertIsNone(p.fn_function(self.event('5c80')))  # too short
        packets = p.message(*p.CMD_KEY_EVENT, bytes(70), 0)
        self.assertIsNone(p.fn_function(packets[1]))  # continuation fragment


class Leds(unittest.TestCase):
    def test_messages(self):
        for msg in LEDS:
            seq, session, entries, last = p.parse_leds(msg)
            with self.subTest(seq=seq):
                self.assertEqual(p.message(*p.CMD_SET_LEDS, p.leds_payload(entries, last),
                                               seq, session), msg)

    def test_complete_updates(self):
        # update() reproduces IO Center's series: 40 entries per message, last one marked
        all_series = list(series(LEDS))
        self.assertEqual(sum(len(s) for s in all_series), len(LEDS))
        for s in all_series:
            seq, session = p.parse_leds(s[0])[:2]
            entries = [e for msg in s for e in p.parse_leds(msg)[2]]
            with self.subTest(seq=seq, entries=len(entries)):
                self.assertEqual(p.update(entries, seq, session), s)

    def test_n_rule(self):
        # N = entries for an intermediate message, entries + 1 followed by 00 for the last one
        entries = [(i, (1, 2, 3)) for i in range(3)]
        self.assertEqual(p.leds_payload(entries, last=False)[0], 3)
        last = p.leds_payload(entries, last=True)
        self.assertEqual((last[0], last[-1], len(last)), (4, 0x00, 1 + 3 * 6 + 1))

    def test_entry_format(self):
        payload = p.leds_payload([(0x2d, (0xff, 0x2a, 0x00))], last=False)
        self.assertEqual(payload, bytes([1, 0x03, 0x2d, 0x00, 0xff, 0x2a, 0x00]))

    def test_seq_wraps(self):
        msgs = p.update([(i, (0, 0, 0)) for i in range(80)], seq=0xff)
        self.assertEqual([m[0][4] for m in msgs], [0xff, 0x00])


class Fragmentation(unittest.TestCase):
    def test_capacities(self):
        # 55 data bytes in the first fragment, 59 in the following ones
        for size, count in ((55, 1), (56, 2), (55 + 59, 2), (55 + 59 + 1, 3)):
            with self.subTest(size=size):
                self.assertEqual(len(p.message(0x10, 0x0d, bytes(size), 0)), count)

    def test_index_and_continuation(self):
        packets = p.message(0x10, 0x0d, bytes(200), 0x42, session=0x03)
        self.assertEqual([pk[1] for pk in packets], [0x80, 0x81, 0x82, 0x03])
        self.assertTrue(all(pk[2] == 0x03 for pk in packets))
        self.assertEqual(packets[0][3:7], bytes([0x00, 0x42, 0x10, 0x0d]))

    def test_reassembly(self):
        payload = bytes(range(200))
        packets = p.message(0x10, 0x0d, payload, 0)
        data = packets[0][7:packets[0][0] + 1] + b''.join(pk[3:pk[0] + 1] for pk in packets[1:])
        self.assertEqual(data, payload)


if __name__ == '__main__':
    unittest.main()
