"""Vendor protocol of the be quiet! Light Mount (interface 2, 64-byte packets). No I/O.

Packet: [len][idx][session][data...][CRC-16/MODBUS LE of bytes 0..61 at 62..63]
  len  = index of the last meaningful byte
  idx  = fragment number (bits 0..6), bit 7 = more fragments follow
The first fragment starts with [00][seq][cmd][sub]: seq only fits in 1 byte.
Each field was identified in captures of the vendor software and checked by replay.
"""
import struct

SESSION = 0x01  # assigned by 01:01 in IO Center; 01 is accepted without opening a session
PACKET_SIZE = 64
FIRST_CAPACITY, NEXT_CAPACITY = 55, 59  # data bytes per fragment

SESSION_NONE = 0x00  # before 01:01

CMD_GET_VERSION = (0x03, 0x01)
CMD_GET_SERIAL = (0x03, 0x02)
CMD_GET_MODE = (0x10, 0x01)      # read the lighting mode
CMD_SET_MODE = (0x10, 0x02)      # no reply with the same seq
CMD_SET_LIGHTING = (0x10, 0x06)  # effect, stored in the keyboard
CMD_SET_LEDS = (0x10, 0x0d)      # per-LED color, volatile
MODE_EFFECTS, MODE_CUSTOM = 0x01, 0x03  # 01: 10:06 applies; 03: 10:0d applies
CMD_KEY_EVENT = (0x11, 0x02)    # spontaneous, one per key press
FN_LAYER = 0x80                 # key event data[1] when Fn is held
FN_EFFECT = 0x09                # Fn-layer function: lighting effect change (Fn+→, 2026-10-15)

EFFECT_STATIC, SPEED_DEFAULT, COLOR_MODE_SINGLE = 0x00, 0x32, 0x00

ENTRY_TAG = 0x03
ENTRIES_PER_MESSAGE = 40  # IO Center's split for a full update


def crc16_modbus(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def packet(idx, session, body):
    raw = bytearray(PACKET_SIZE)
    raw[0] = 2 + len(body)
    raw[1], raw[2] = idx, session
    raw[3:3 + len(body)] = body
    raw[62:64] = struct.pack('<H', crc16_modbus(raw[:62]))
    return bytes(raw)


def message(cmd, sub, payload, seq, session=SESSION):
    """Split a message into 64-byte fragments."""
    head = struct.pack('>H', seq) + bytes([cmd, sub])
    chunks = [payload[:FIRST_CAPACITY]]
    rest = payload[FIRST_CAPACITY:]
    while rest:
        chunks.append(rest[:NEXT_CAPACITY])
        rest = rest[NEXT_CAPACITY:]
    packets = []
    for i, chunk in enumerate(chunks):
        more = 0x80 if i < len(chunks) - 1 else 0x00
        body = (head + chunk) if i == 0 else chunk
        packets.append(packet(more | i, session, body))
    return packets


def frame(cmd, sub, payload, seq, session=SESSION):
    """Single-packet message."""
    (raw,) = message(cmd, sub, payload, seq, session)
    return raw


def crc_ok(raw):
    return struct.unpack('<H', raw[62:64])[0] == crc16_modbus(raw[:62])


def is_reply(resp, request):
    """Reply with the same seq and cmd:sub."""
    return resp[3:7] == request[3:7]


# --- 03:01 / 03:02: identification ----------------------------------------------
# IO Center sends both before opening a session (01:01), with session byte 00.

def get_version(seq):
    return frame(*CMD_GET_VERSION, b'', seq, SESSION_NONE)


def version_of(resp):
    """03:01 reply data: 8 bytes, identical in every capture (firmware version, presumably)."""
    return bytes(resp[7:resp[0] + 1])


def get_serial(seq):
    return frame(*CMD_GET_SERIAL, b'', seq, SESSION_NONE)


def serial_of(resp):
    """03:02 reply data: [length] then ASCII, specific to each keyboard (serial number, presumably)."""
    data = resp[7:resp[0] + 1]
    return bytes(data[1:1 + data[0]]).decode('ascii', 'replace')


# --- 10:01 / 10:02: lighting mode -------------------------------------------

def get_mode(seq, session=SESSION):
    return frame(*CMD_GET_MODE, b'', seq, session)


def mode_of(resp):
    return resp[7]


def set_mode(mode, seq, session=SESSION):
    return frame(*CMD_SET_MODE, bytes([mode]), seq, session)


# --- 11:02: key events -------------------------------------------------------
#   plain key: [vendor key index][00][01][01][00][HID usage]
#   Fn layer:  [vendor key index][80][01][function]...   (Fn alone: function 1b)

def fn_function(raw):
    """Function code of an Fn-layer key event, or None for anything else (plain keys included)."""
    if raw[1] & 0x7f or tuple(raw[5:7]) != CMD_KEY_EVENT or raw[0] < 10:
        return None
    return raw[10] if raw[8] == FN_LAYER else None


# --- 10:06: static effect -----------------------------------------------------

def static_color(rgb, brightness, seq, session=SESSION):
    payload = bytes([0x00, EFFECT_STATIC, 0x00, brightness, SPEED_DEFAULT, COLOR_MODE_SINGLE, *rgb])
    return frame(*CMD_SET_LIGHTING, payload, seq, session)


# --- 10:0d: per-LED color -----------------------------------------------------
#   [N] N × [03][index][00][R][G][B] [00 if last message]
#   N = number of entries, +1 for the last message of an update

def leds_payload(entries, last):
    body = b''.join(bytes([ENTRY_TAG, idx, 0x00, *rgb]) for idx, rgb in entries)
    if last:
        return bytes([len(entries) + 1]) + body + b'\x00'
    return bytes([len(entries)]) + body


def update(entries, seq, session=SESSION):
    """Update: messages of 40 entries, the last one marked. Returns a list of messages."""
    entries = list(entries)
    batches = [entries[i:i + ENTRIES_PER_MESSAGE] for i in range(0, len(entries), ENTRIES_PER_MESSAGE)]
    out = []
    for i, batch in enumerate(batches):
        last = i == len(batches) - 1
        out.append(message(*CMD_SET_LEDS, leds_payload(batch, last), (seq + i) & 0xFF, session))
    return out


def parse_leds(packets):
    """10:0d message → (seq, session, entries, last)."""
    first = packets[0]
    data = bytearray(first[7:first[0] + 1])
    for p in packets[1:]:
        data += p[3:p[0] + 1]
    n = data[0]
    entries, i = [], 1
    while i + 6 <= len(data) and data[i] == ENTRY_TAG:
        entries.append((data[i + 1], tuple(data[i + 3:i + 6])))
        i += 6
    last = n == len(entries) + 1
    return struct.unpack('>H', first[3:5])[0], first[2], entries, last
