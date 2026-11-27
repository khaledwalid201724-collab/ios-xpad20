#!/usr/bin/env python3
"""Extract hardware facts from a flat device-tree dump — no dtc needed.

Read-only, host-side. Reads /sys/firmware/fdt (or a DTB from the stock boot
image) and prints the nodes the port needs: GPU, MSDC/eMMC, display/panel,
touch, gpio-keys, PMIC, memory and interrupts.

Usage:
    tools/facts-from-dtb.py DUMP.dtb [--out work/xpad20/facts.txt]

Get DUMP.dtb with (after adb is installed and USB debugging is on):
    adb exec-out cat /sys/firmware/fdt > work/xpad20/fdt.dtb
"""
import argparse
import struct
import sys

FDT_MAGIC = 0xD00DFEED
BEGIN_NODE, END_NODE, PROP, NOP, END = 1, 2, 3, 4, 9

INTERESTING = (
    # GPU / storage
    'gpu', 'mali', 'bifrost', 'g3d', 'msdc', 'mmc', 'sdhci', 'emmc', 'ufs',
    # input
    'touch', 'tcm', 'synaptics', 'melfas', 'goodix', 'novatek', 'ov', 'td4160',
    'gpio-keys', 'key', 'volume', 'power',
    # display
    'fb', 'framebuffer', 'decon', 'dpu', 'dpi', 'dsi', 'panel', 'lcd', 'display',
    # SoC basics
    'memory', 'chosen', 'pmic', 'mt6358', 'mt6360', 'mt6315', 'fuelgauge',
    'battery', 'timer', 'gic', 'interrupt-controller', 'usb', 'serial',
    'mt6769', 'mt6768', 'connsys', 'scp',
)


class Node:
    def __init__(self, name):
        self.name = name
        self.props = {}
        self.children = []

    def prop_str(self, key):
        v = self.props.get(key)
        return v.split(b'\0')[0].decode(errors='replace') if v else ''


def parse_fdt(buf):
    if len(buf) < 40 or struct.unpack_from('>I', buf, 0)[0] != FDT_MAGIC:
        raise SystemExit('not a flat device tree (bad magic)')
    (_, total, off_struct, off_strings, off_mem, ver, last, cpu,
     size_strings, size_struct) = struct.unpack_from('>10I', buf, 0)
    if off_struct + size_struct > len(buf) or off_strings + size_strings > len(buf):
        raise SystemExit('truncated device tree')
    strings = buf[off_strings:off_strings + size_strings]

    def sname(off):
        if off >= len(strings):
            return f'?{off}'
        return strings[off:strings.find(b'\0', off)].decode(errors='replace')

    root = None
    stack = []
    off = off_struct
    while off < off_struct + size_struct:
        tag, = struct.unpack_from('>I', buf, off)
        off += 4
        if tag == BEGIN_NODE:
            end = buf.find(b'\0', off)
            name = buf[off:end].decode(errors='replace')
            off = (end + 4) & ~3
            node = Node(name)
            if stack:
                stack[-1].children.append(node)
            else:
                root = node
            stack.append(node)
        elif tag == PROP:
            ln, nameoff = struct.unpack_from('>II', buf, off)
            off += 8
            value = buf[off:off + ln]
            off = (off + ln + 3) & ~3
            if stack:
                stack[-1].props[sname(nameoff)] = value
        elif tag == END_NODE:
            if stack:
                stack.pop()
        elif tag == NOP:
            continue
        elif tag == END:
            break
        else:
            raise SystemExit(f'unknown FDT token {tag:#x} at {off:#x}')
    if root is None:
        raise SystemExit('no root node in device tree')
    return root, buf[off_mem:off_struct]


def fmt_bytes(v, maxints=16):
    if v is None:
        return '?'
    if len(v) % 4 == 0 and len(v) <= maxints * 4:
        words = struct.unpack(f'>{len(v) // 4}I', v)
        return '<' + ' '.join(hex(w) for w in words) + '>'
    return v[:48].hex() + ('...' if len(v) > 48 else '')


def interesting(node):
    hay = node.name.lower() + ' ' + node.prop_str('compatible').lower()
    return any(k in hay for k in INTERESTING)


def walk(node, depth=0, out=None):
    if out is None:
        out = []
    if interesting(node):
        line = ['  ' * depth + node.name + ':']
        comp = node.prop_str('compatible')
        if comp:
            line.append('  ' * (depth + 1) + f'compatible = {comp!r}')
        for key in ('reg', 'interrupts', 'ranges', 'clocks', 'clock-frequency',
                    'status', 'model', 'non-removable', 'fifo-depth',
                    'mediatek,gpio', 'irq-gpio', 'interrupt-parent',
                    'timebase-frequency'):
            if key in node.props:
                line.append('  ' * (depth + 1) + f'{key} = {fmt_bytes(node.props[key])}')
        out.extend(line)
    for child in node.children:
        walk(child, depth + 1, out)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('dtb', help='dump of /sys/firmware/fdt, or a DTB from boot')
    p.add_argument('--out', type=argparse.FileType('w'), default=sys.stdout)
    args = p.parse_args()

    buf = open(args.dtb, 'rb').read()
    root, mem = parse_fdt(buf)
    w = args.out.write

    w('=== Infinix XPad 20 device-tree facts (candidate extraction) ===\n')
    w(f'source: {args.dtb}\n')
    w(f'root compatible: {root.prop_str("compatible")!r}\n')
    w(f'model: {root.prop_str("model")!r}\n\n')

    w('--- memory reserve entries ---\n')
    for i in range(0, len(mem) - 15, 16):
        addr, size = struct.unpack_from('>QQ', mem, i)
        if addr or size:
            w(f'  {addr:#018x} + {size:#x}\n')

    w('\n--- relevant nodes ---\n')
    for line in walk(root):
        w(line + '\n')

    w('\n--- what to fill in next ---\n')
    w('GPU MMIO + IRQ, MSDC/eMMC controller, framebuffer address, panel size,\n')
    w('touch controller and gpio-keys from the numbers above feed the ADT and\n')
    w('the board drivers. Compare with 0xBEEBAD/hakios-mt6768 (MT6768 sibling).\n')


if __name__ == '__main__':
    main()
