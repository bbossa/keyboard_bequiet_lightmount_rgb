"""Device discovery and identification against a fake sysfs and a simulated keyboard."""
import os, shutil, socket, tempfile, threading, unittest
from unittest import mock

import fixtures
from lightmount import device, hid, protocol as p

DESCRIPTORS = os.path.join(fixtures.HERE, 'fixtures', 'descriptors')  # report descriptors read from sysfs
KNOWN_VERSION = bytes.fromhex('0200010100000302')
SERIAL = 'TEST0000000042'


def descriptor(interface):
    with open(os.path.join(DESCRIPTORS, f'if{interface}.bin'), 'rb') as f:
        return f.read()


class FakeSysfs:
    """Tree shaped like /sys: class/hidraw/hidrawN/device -> devices/.../<usb>/<usb>:1.<i>/<hid instance>."""

    def __init__(self):
        self.root = tempfile.mkdtemp(prefix='lightmount-sysfs-')
        self.count = 0
        os.makedirs(os.path.join(self.root, 'class', 'hidraw'))

    def add(self, usb_path, interfaces=(0, 1, 2, 3), hid_id=device.HID_ID, descriptors=None):
        descriptors = descriptors or {}
        for i in interfaces:
            instance = f'{hid_id[:4]}:{hid_id[9:13]}:{hid_id[18:]}.{self.count:04X}'
            hid_dir = os.path.join(self.root, 'devices', 'usb1', usb_path, f'{usb_path}:1.{i}', instance)
            os.makedirs(hid_dir)
            with open(os.path.join(hid_dir, '..', 'bInterfaceNumber'), 'w') as f:
                f.write(f'{i:02x}\n')
            with open(os.path.join(hid_dir, 'uevent'), 'w') as f:
                f.write(f'DRIVER=hid-generic\nHID_ID={hid_id}\nHID_PHYS=usb-test-{usb_path}/input{i}\n')
            with open(os.path.join(hid_dir, 'report_descriptor'), 'wb') as f:
                f.write(descriptors.get(i, descriptor(i)))
            node = os.path.join(self.root, 'class', 'hidraw', f'hidraw{self.count}')
            os.makedirs(node)
            os.symlink(hid_dir, os.path.join(node, 'device'))
            self.count += 1

    def remove(self):
        shutil.rmtree(self.root)


class FakeKeyboard:
    """Answers like the Light Mount on a SOCK_SEQPACKET pair (one read = one report)."""

    def __init__(self, version=KNOWN_VERSION, serial=SERIAL, mode=p.MODE_CUSTOM):
        self.version, self.serial, self.mode = version, serial, mode
        self.opened, self.received = [], []

    def open(self, path, flags, *args, **kwargs):
        if not str(path).startswith('/dev/hidraw'):
            return real_open(path, flags, *args, **kwargs)
        self.opened.append(path)
        ours, theirs = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        threading.Thread(target=self.serve, args=(theirs,), daemon=True).start()
        return ours.detach()

    def serve(self, sock):
        with sock:
            while data := sock.recv(65):
                raw = data[1:]  # report ID 0
                self.received.append(raw)
                cmd, seq, session = (raw[5], raw[6]), raw[4], raw[2]
                payload = {p.CMD_GET_VERSION: self.version,
                           p.CMD_GET_SERIAL: bytes([len(self.serial)]) + self.serial.encode(),
                           p.CMD_GET_MODE: bytes([self.mode]), p.CMD_SET_LIGHTING: b''}.get(cmd)
                if payload is not None:
                    sock.send(p.frame(*cmd, payload, seq, session))

    def commands(self):
        return [(raw[5], raw[6]) for raw in self.received if raw[1] & 0x7f == 0]


real_open = os.open


class DeviceTest(unittest.TestCase):
    def setUp(self):
        self.sysfs = FakeSysfs()
        self.addCleanup(self.sysfs.remove)
        patcher = mock.patch.object(device, 'SYSFS', self.sysfs.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        device._identities.clear()

    def keyboard(self, **kwargs):
        kb = FakeKeyboard(**kwargs)
        patcher = mock.patch.object(device.os, 'open', kb.open)
        patcher.start()
        self.addCleanup(patcher.stop)
        return kb


class Descriptors(unittest.TestCase):
    def test_saved_descriptors(self):
        expected = {0: (0x01, 0x06), 1: (0x01, 0x06), 2: (0xff00, 0x01), 3: (0x59, 0x01)}
        for interface, usage in expected.items():
            self.assertEqual(hid.top_level_usage(descriptor(interface)), usage)

    def test_no_collection(self):
        self.assertIsNone(hid.top_level_usage(bytes.fromhex('0600ff0901')))


class Find(DeviceTest):
    def test_none(self):
        with self.assertRaisesRegex(device.DeviceError, 'not found'):
            device.find({})

    def test_single(self):
        self.sysfs.add('1-7.2')
        kb = device.find({})
        self.assertEqual(kb.usb_path, '1-7.2')
        self.assertEqual(kb.vendor, '/dev/hidraw2')
        self.assertEqual(kb.hidraw[device.LAMPARRAY_INTERFACE], '/dev/hidraw3')

    def test_other_devices_ignored(self):
        self.sysfs.add('1-3', hid_id='0003:0000046D:0000C52B')
        self.sysfs.add('1-7.2')
        self.assertEqual(device.find({}).usb_path, '1-7.2')

    def test_several_refused(self):
        self.sysfs.add('1-7.2')
        self.sysfs.add('1-8')
        with self.assertRaisesRegex(device.DeviceError, r'several.*1-7\.2, 1-8.*usb_path'):
            device.find({})

    def test_several_chosen(self):
        self.sysfs.add('1-7.2')
        self.sysfs.add('1-8')
        kb = device.find({'device': {'usb_path': '1-8'}})
        self.assertEqual((kb.usb_path, kb.vendor), ('1-8', '/dev/hidraw6'))

    def test_chosen_absent(self):
        self.sysfs.add('1-7.2')
        with self.assertRaisesRegex(device.DeviceError, r'usb_path = "1-8".*present: 1-7\.2'):
            device.find({'device': {'usb_path': '1-8'}})

    def test_missing_interface(self):
        self.sysfs.add('1-7.2', interfaces=(0, 1, 2))
        with self.assertRaisesRegex(device.DeviceError, 'interface 3 missing'):
            device.find({})

    def test_unexpected_descriptor(self):
        self.sysfs.add('1-7.2', descriptors={2: descriptor(0)})
        with self.assertRaisesRegex(device.DeviceError, 'unexpected report descriptor on interface 2'):
            device.find({})

    def test_unexpected_descriptor_writes_nothing(self):
        self.sysfs.add('1-7.2', descriptors={3: descriptor(1)})
        kb = self.keyboard()
        with self.assertRaises(device.DeviceError):
            device.send_leds({}, [(0x2d, (1, 2, 3))])
        self.assertEqual(kb.opened, [])


class Identification(DeviceTest):
    def test_known_version_writes(self):
        self.sysfs.add('1-7.2')
        kb = self.keyboard()
        device.send_leds({}, [(0x2d, (1, 2, 3))])
        self.assertEqual(kb.commands(), [p.CMD_GET_VERSION, p.CMD_GET_SERIAL, p.CMD_GET_MODE, p.CMD_SET_LEDS])

    def test_requests_as_captured(self):
        # same frames as IO Center Web (session 00), only seq differs
        self.sysfs.add('1-7.2')
        kb = self.keyboard()
        device.send_leds({}, [(0x2d, (1, 2, 3))])
        version, serial = kb.received[:2]
        self.assertEqual(version, p.get_version(version[4]))
        self.assertEqual(serial, p.get_serial(serial[4]))
        self.assertEqual(version[2], p.SESSION_NONE)

    def test_unknown_version_read_only(self):
        self.sysfs.add('1-7.2')
        kb = self.keyboard(version=bytes.fromhex('0200010100000303'))
        with self.assertLogs('lightmount', 'WARNING') as logs, \
                self.assertRaisesRegex(device.ReadOnlyError, 'unknown version'):
            device.send_leds({}, [(0x2d, (1, 2, 3))])
        self.assertEqual(kb.commands(), [p.CMD_GET_VERSION, p.CMD_GET_SERIAL])
        self.assertIn('read-only', logs.output[0])

    def test_unknown_version_static_refused(self):
        self.sysfs.add('1-7.2')
        kb = self.keyboard(version=b'\x99')
        with self.assertRaises(device.ReadOnlyError):
            device.set_static({}, b'\xe6\x30\x00', 50)
        self.assertEqual(kb.commands(), [p.CMD_GET_VERSION, p.CMD_GET_SERIAL])

    def test_unknown_version_forced(self):
        self.sysfs.add('1-7.2')
        kb = self.keyboard(version=b'\x99')
        with self.assertLogs('lightmount', 'WARNING'):
            device.send_leds({'device': {'allow_unknown_firmware': True}}, [(0x2d, (1, 2, 3))])
        self.assertEqual(kb.commands()[-1], p.CMD_SET_LEDS)

    def test_identified_once_per_plug(self):
        self.sysfs.add('1-7.2')
        kb = self.keyboard()
        self.first_instance = device.find({}).instance
        device.send_leds({}, [(0x2d, (1, 2, 3))])
        device.send_leds({}, [(0x2d, (1, 2, 3))])
        self.assertEqual(kb.commands().count(p.CMD_GET_VERSION), 1)
        # replug: same port, new HID instance, identified again
        replugged = FakeSysfs()
        self.addCleanup(replugged.remove)
        replugged.count = 4
        replugged.add('1-7.2')
        with mock.patch.object(device, 'SYSFS', replugged.root):
            self.assertNotEqual(device.find({}).instance, self.first_instance)
            device.send_leds({}, [(0x2d, (1, 2, 3))])
        self.assertEqual(kb.commands().count(p.CMD_GET_VERSION), 2)

    def test_serial_never_logged(self):
        self.sysfs.add('1-7.2')
        self.keyboard()
        with self.assertLogs('lightmount', 'DEBUG') as logs:
            device.send_leds({}, [(0x2d, (1, 2, 3))])
        self.assertTrue(logs.output)
        self.assertFalse(any(SERIAL in line for line in logs.output))

    def test_no_reply(self):
        self.sysfs.add('1-7.2')
        kb = self.keyboard()
        kb.version = None  # the fake keyboard stays silent on 03:01
        with mock.patch.object(device, 'REPLY_TIMEOUT', 0.05), \
                self.assertRaisesRegex(device.DeviceError, 'no valid reply'):
            device.send_leds({}, [(0x2d, (1, 2, 3))])
        self.assertEqual(kb.commands(), [p.CMD_GET_VERSION])


if __name__ == '__main__':
    unittest.main()
