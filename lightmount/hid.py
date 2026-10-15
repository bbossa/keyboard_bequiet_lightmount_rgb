"""Minimal HID report descriptor parsing (short items only). No I/O."""

TYPE_MAIN, TYPE_GLOBAL, TYPE_LOCAL = 0, 1, 2
TAG_COLLECTION = 0xa
TAG_USAGE_PAGE = 0x0  # global
TAG_USAGE = 0x0       # local


def items(descriptor):
    """(type, tag, value) of each short item."""
    i = 0
    while i < len(descriptor):
        prefix = descriptor[i]
        if prefix == 0xfe:  # long item: [fe][size][tag][data...]
            i += 3 + descriptor[i + 1]
            continue
        size = (0, 1, 2, 4)[prefix & 3]
        value = int.from_bytes(descriptor[i + 1:i + 1 + size], 'little')
        yield (prefix >> 2) & 3, prefix >> 4, value
        i += 1 + size


def top_level_usage(descriptor):
    """(usage page, usage) of the first collection, or None."""
    page = usage = None
    for kind, tag, value in items(descriptor):
        if kind == TYPE_GLOBAL and tag == TAG_USAGE_PAGE:
            page = value
        elif kind == TYPE_LOCAL and tag == TAG_USAGE:
            usage = value
        elif kind == TYPE_MAIN and tag == TAG_COLLECTION:
            return page, usage
    return None
