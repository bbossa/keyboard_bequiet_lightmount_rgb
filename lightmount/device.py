"""hidraw access to the Light Mount vendor interface (interface 2).

Nothing is written unless the device is the expected one:
  1. USB ID 373f:0002 and both interfaces present with the expected report
     descriptor (interface 2 vendor 0xFF00, interface 3 LampArray 0x59): sysfs only;
  2. a single keyboard, or the one chosen with [device] usb_path;
  3. a known version (03:01 reply); otherwise read-only unless
     [device] allow_unknown_firmware = true.
"""
import glob, hashlib, logging, os, select, time
from contextlib import contextmanager
from dataclasses import dataclass

from . import hid, protocol as p

log = logging.getLogger('lightmount')

SYSFS = '/sys'
HID_ID = '0003:0000373F:00000002'
VENDOR_INTERFACE, LAMPARRAY_INTERFACE = 2, 3
EXPECTED_USAGES = {VENDOR_INTERFACE: (0xff00, 0x01), LAMPARRAY_INTERFACE: (0x59, 0x01)}
KNOWN_VERSIONS = {bytes.fromhex('0200010100000302')}  # 03:01 reply of the tested keyboard
REPLY_TIMEOUT = 1.0


class DeviceError(Exception):
    pass


class ReadOnlyError(DeviceError):
    pass


@dataclass(frozen=True)
class Keyboard:
    usb_path: str   # sysfs USB device name (port path), e.g. 1-7.2
    hidraw: dict    # interface number -> /dev/hidrawN
    instance: str   # sysfs HID instance of the vendor interface, changes on every replug

    @property
    def vendor(self):
        return self.hidraw[VENDOR_INTERFACE]


@dataclass(frozen=True)
class Identity:
    version: bytes
    serial_hash: str  # never log the serial itself

    @property
    def known(self):
        return self.version in KNOWN_VERSIONS


def scan():
    """Light Mount HID interfaces grouped by USB device: {usb_path: {interface: (node, hid_dir)}}."""
    found = {}
    for node_dir in sorted(glob.glob(os.path.join(SYSFS, 'class/hidraw/hidraw*'))):
        hid_dir = os.path.realpath(os.path.join(node_dir, 'device'))
        try:
            with open(os.path.join(hid_dir, 'uevent')) as f:
                if f'HID_ID={HID_ID}\n' not in f.read():
                    continue
            interface_dir = os.path.dirname(hid_dir)
            with open(os.path.join(interface_dir, 'bInterfaceNumber')) as f:
                interface = int(f.read(), 16)
        except (OSError, ValueError):  # unplugged while scanning, or not a USB interface
            continue
        usb_path = os.path.basename(os.path.dirname(interface_dir))
        found.setdefault(usb_path, {})[interface] = ('/dev/' + os.path.basename(node_dir), hid_dir)
    return found


def check_interfaces(usb_path, interfaces):
    for interface, usage in EXPECTED_USAGES.items():
        if interface not in interfaces:
            raise DeviceError(f'Light Mount {usb_path}: interface {interface} missing')
        with open(os.path.join(interfaces[interface][1], 'report_descriptor'), 'rb') as f:
            actual = hid.top_level_usage(f.read())
        if actual != usage:
            raise DeviceError(f'Light Mount {usb_path}: unexpected report descriptor on interface '
                              f'{interface} (usage {fmt_usage(actual)}, expected {fmt_usage(usage)})')


def fmt_usage(usage):
    return 'none' if usage is None else f'{usage[0]:#06x}/{usage[1]:#04x}'


def find(cfg):
    """The keyboard to drive, checked against its report descriptors. Writes nothing."""
    found = scan()
    wanted = cfg.get('device', {}).get('usb_path', '')
    if not found:
        raise DeviceError('Light Mount not found (USB 373f:0002)')
    if wanted:
        if wanted not in found:
            raise DeviceError(f'Light Mount not found at usb_path = "{wanted}" '
                              f'(present: {", ".join(sorted(found))})')
        usb_path = wanted
    elif len(found) > 1:
        raise DeviceError(f'several Light Mount keyboards ({", ".join(sorted(found))}): '
                          'choose one with usb_path in the [device] section of the config')
    else:
        (usb_path,) = found
    interfaces = found[usb_path]
    check_interfaces(usb_path, interfaces)
    return Keyboard(usb_path, {i: node for i, (node, _) in interfaces.items()},
                    os.path.basename(interfaces[VENDOR_INTERFACE][1]))


# --- I/O ----------------------------------------------------------------------

def write(fd, packets):
    for raw in packets:
        os.write(fd, b'\x00' + raw)  # report ID 0: the interface declares none


def read_reply(fd, request, timeout=None):
    """First reply with the same seq and cmd:sub as `request`, or None."""
    deadline = time.monotonic() + (REPLY_TIMEOUT if timeout is None else timeout)
    while (left := deadline - time.monotonic()) > 0 and select.select([fd], [], [], left)[0]:
        resp = os.read(fd, p.PACKET_SIZE)
        if p.is_reply(resp, request):
            return resp
    return None


def request(fd, raw):
    write(fd, [raw])
    return read_reply(fd, raw)


def new_seq():
    return int(time.time()) & 0xFF


def identify(fd, seq):
    """Version (03:01) and hashed serial (03:02), as IO Center reads them first."""
    resp = request(fd, p.get_version(seq))
    if resp is None or not p.crc_ok(resp):
        raise DeviceError('Light Mount: no valid reply to the version request (03:01)')
    version = p.version_of(resp)
    resp = request(fd, p.get_serial((seq + 1) & 0xFF))
    serial = p.serial_of(resp) if resp is not None and p.crc_ok(resp) else ''
    return Identity(version, hashlib.sha256(serial.encode()).hexdigest()[:12] if serial else 'none')


_identities = {}  # Keyboard.instance -> Identity, read once per plug


@contextmanager
def vendor(cfg, writing=True):
    """Open the vendor interface; refuse writing to an unknown version unless allowed."""
    kb = find(cfg)
    fd = os.open(kb.vendor, os.O_RDWR)
    try:
        ident = _identities.get(kb.instance)
        if ident is None:
            ident = _identities[kb.instance] = identify(fd, new_seq())
            log.debug('Light Mount %s on %s: version %s, serial #%s',
                      kb.usb_path, kb.vendor, ident.version.hex(' '), ident.serial_hash)
            if not ident.known:
                log.warning('Light Mount %s: unknown version %s (known: %s); read-only unless '
                            'allow_unknown_firmware = true in [device]', kb.usb_path,
                            ident.version.hex(' '), ', '.join(v.hex(' ') for v in sorted(KNOWN_VERSIONS)))
        if writing and not ident.known and not cfg.get('device', {}).get('allow_unknown_firmware', False):
            raise ReadOnlyError(f'Light Mount {kb.usb_path}: unknown version {ident.version.hex(" ")}, '
                                'nothing written (allow_unknown_firmware = true in [device] to force)')
        yield fd
    finally:
        os.close(fd)


def read_mode(fd, seq):
    """Lighting mode (10:01), read like IO Center does before any change."""
    resp = request(fd, p.get_mode(seq))
    return None if resp is None else p.mode_of(resp)


def send_leds(cfg, entries):
    """Per-LED colors (10:0d), switching to custom mode if needed."""
    with vendor(cfg) as fd:
        seq = new_seq()
        # Switching to custom mode resets every LED: only do it when needed.
        if read_mode(fd, seq) != p.MODE_CUSTOM:
            write(fd, [p.set_mode(p.MODE_CUSTOM, (seq + 1) & 0xFF)])
            time.sleep(0.05)
        seq = (seq + 2) & 0xFF
        for msg in p.update(entries, seq):
            write(fd, msg)
            time.sleep(0.01)


def send_frame(fd, raw, expect_reply=True):
    """Send one packet; True if a reply with a valid CRC comes back (or none is expected)."""
    write(fd, [raw])
    if not expect_reply:  # 10:02 sends no reply with the same seq
        time.sleep(0.05)
        return True
    resp = read_reply(fd, raw)
    return resp is not None and p.crc_ok(resp)


def set_static(cfg, rgb, brightness):
    """Static effect (10:06), after switching back to effects mode. Stored in the keyboard."""
    with vendor(cfg) as fd:
        seq = new_seq()
        send_frame(fd, p.set_mode(p.MODE_EFFECTS, seq), expect_reply=False)
        return send_frame(fd, p.static_color(rgb, brightness, (seq + 1) & 0xFF))


def status(cfg):
    """(keyboard, identity, lighting mode or None). Sends only read requests (03:01, 03:02, 10:01)."""
    kb = find(cfg)
    with vendor(cfg, writing=False) as fd:
        mode = read_mode(fd, new_seq())
    return kb, _identities[kb.instance], mode
