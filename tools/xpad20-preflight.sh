#!/usr/bin/env bash
# Read-only Infinix XPad 20 (X1102, Helio G88 / MT6769) fact collection.
# No flashing, no reboot, no root required (some logs may be unavailable).
# Output goes under work/xpad20/ (git-ignored): may contain device serials.
set -eu

command -v adb >/dev/null 2>&1 || {
    echo "adb not found; install Android platform-tools first." >&2
    echo "  Debian/Ubuntu: sudo apt install android-tools-adb" >&2
    exit 1;
}

devices=$(adb devices | awk 'NR>1 && $2 == "device" {print $1}')
count=$(printf '%s\n' "$devices" | grep -c . || true)
if [ "$count" -ne 1 ]; then
    echo "Expected exactly one device in 'adb devices', found $count." >&2
    echo "Connect the XPad 20 and enable USB debugging." >&2
    exit 1
fi

outdir="work/xpad20/preflight-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$outdir"
echo "Writing read-only device facts to $outdir (not committed)."

adb shell getprop > "$outdir/getprop.txt"
adb shell cat /proc/cpuinfo > "$outdir/cpuinfo.txt"
adb shell cat /proc/partitions > "$outdir/partitions.txt" 2>/dev/null || true
adb shell df -h > "$outdir/df.txt" 2>/dev/null || true
adb shell cat /proc/mounts > "$outdir/mounts.txt" 2>/dev/null || true
adb shell cat /proc/interrupts > "$outdir/interrupts.txt" 2>/dev/null || true
adb shell dmesg 2>/dev/null | grep -iE 'mali|panfrost|gpu|msdc|mmc|emmc|dtb|fdt|display|panel|touch' \
    > "$outdir/dmesg-hardware.txt" || true

{
    echo "== Identity =="
    grep -iE 'ro.product.model|ro.product.brand|ro.product.device|ro.build.version|ro.build.id|ro.bootloader|ro.boot.verifiedbootstate|ro.boot.flash.locked|sys.boot_completed' \
        "$outdir/getprop.txt" || true
    echo
    echo "== Storage controller (is it eMMC/MSDC or UFS?) =="
    grep -iE 'mmc|emmc|sdc|ufs|msdc' "$outdir/mounts.txt" "$outdir/dmesg-hardware.txt" 2>/dev/null | head -40 || true
    echo
    echo "== GPU properties and sysfs =="
    grep -iE 'gpu|mali|gles|vulkan|render|ro.hardware' "$outdir/getprop.txt" || true
    for node in \
        /sys/class/misc/mali0 \
        /sys/devices/platform/13000000.gpu \
        /sys/devices/platform/soc/13000000.gpu \
        /sys/kernel/debug/mali0 \
        /proc/gpu; do
        adb shell "ls -ld $node" 2>/dev/null || true
    done
    for file in \
        /sys/kernel/debug/mali0/gpu_id \
        /sys/class/misc/mali0/device/gpu_id \
        /sys/module/mali_kbase/parameters/gpu_id; do
        value=$(adb shell "cat $file" 2>/dev/null || true)
        [ -n "$value" ] && echo "$file: $value"
    done
    echo
    echo "== Display =="
    adb shell wm size 2>/dev/null || true
    adb shell dumpsys display 2>/dev/null | grep -iE 'mBaseDisplayInfo|width|height|refreshRate|density' | head -20 || true
    echo
    echo "== MTK boot / partition names =="
    adb shell ls -l /dev/block/by-name 2>/dev/null | head -60 || true
} | tee "$outdir/summary.txt"

# The live device tree is authoritative for MMIO, IRQs, clocks and panel data.
adb exec-out cat /sys/firmware/fdt > "$outdir/fdt.dtb" 2>/dev/null || \
    echo "Could not read /sys/firmware/fdt; dump it from recovery instead." >&2
if [ -s "$outdir/fdt.dtb" ]; then
    strings "$outdir/fdt.dtb" | grep -iE 'mali|bifrost|gpu|msdc|mmc|emmc|panel|lcd|dsi|touch|keys|mt6769|mt6768' \
        > "$outdir/fdt-hardware-strings.txt" || true
    echo "Device-tree strings saved to $outdir/fdt-hardware-strings.txt"
    echo "Parse it with: tools/facts-from-dtb.py $outdir/fdt.dtb"
fi

echo
echo "Nothing was flashed, unlocked, formatted or rebooted."
