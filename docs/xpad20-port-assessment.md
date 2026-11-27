# Infinix XPad 20 port assessment

**Status: research only (2026-11-27).** There is no bootable XPad 20 image here.
This project is a fresh start from upstream `dipa-studio/ios-sweet`; the earlier
Galaxy F13 work was deleted. This document records what must be built before
iOS/XNU can run on this tablet.

## Hardware (public specifications — verify on the actual device)

| Item | Infinix XPad 20 |
| --- | --- |
| Model | **X1102** (confirm `Settings → About tablet`) |
| SoC | MediaTek **Helio G88**, 2× Cortex-A75 @ 2.0 GHz + 6× Cortex-A55 @ 1.8 GHz, 12 nm |
| SoC code name | MT6769 family (close to MT6768 Helio G85/G80) |
| GPU | **Mali-G52 MC2** ("2EEMC2"), Bifrost v7, up to 1 GHz |
| RAM | 4 / 6 / 8 GB LPDDR4X |
| Storage | 128 / 256 GB — **likely eMMC 5.1**, verify (`/proc/mounts`, `ls /sys/class/mmc_host`) |
| Display | 11" IPS LCD, **1200×1920**, 60/90 Hz |
| Battery | 7000 mAh |
| OS | Android 15, XOS 15 |
| Connectivity | 4G LTE, Wi-Fi, Bluetooth 5.2, USB-C, microSD |
| Boot | MediaTek preloader → LK → `boot_a`. Unlocked bootloader gives `fastboot`, unlike Samsung Download Mode |

Public sources: [Infinix official specs](https://wap.infinixmobility.com/specs/xpad-20),
[GSMArena](https://gsmarena.com/infinix_xpad_20-13922.php),
[MediaTek Helio G88](https://www.mediatek.com/products/smartphones/mediatek-helio-g88).

## Why upstream `ios-sweet` cannot boot it as-is

1. **Boot path.** `shim/` is packed as an Android boot.img v2 and launched with
   `fastboot boot`. On MediaTek the chain is preloader → LK → `boot_a`; the
   loader has to be placed in `boot_a` and started there. There is a working
   example (below) that boots XNU from `boot_a` and returns to Android after
   every run.
2. **Storage.** The current tree carries a Qualcomm UFS host driver. The XPad 20
   likely uses eMMC through an MTK MSDC controller. That driver must be ported.
3. **Board hardware.** Early console, framebuffer, GIC/timer, eMMC and USB glue
   use Qualcomm register addresses; they need MT6769 equivalents from the live
   device tree and MediaTek/Infinix kernel source.
4. **GPU.** Sweet's Adreno path is useless here. The Mali-G52 needs a Panfrost
   kernel/uAPI shim plus Mesa and an EAGL/Metal bridge — but this is *more*
   realistic than the F13 because a working MT6768 Mali-G52 stack exists.
5. **Display / touch / buttons.** 1200×1920 @90 Hz panel, unknown touch
   controller and PMIC/fuel gauge. All must be read from the device tree.

The generic XNU patches, iPhone X iOS 16 userland, HFS, launchd handling and
Settings/activation workarounds carry over regardless of SoC. This is still
days-to-weeks of board work, not a config edit, and it needs the physical tablet
for every boot test.

## Recommended base

**[`0xBEEBAD/hakios-mt6768`](https://github.com/0xBEEBAD/hakios-mt6768)** —
HakiOS for the Infinix Hot 20 (X6826B), MediaTek Helio G85 (MT6768), Mali-G52
MC2, eMMC. This is the closest available base: same vendor, same SoC family,
same GPU, same storage type. Its README (checked 2026-11-27) reports working:

- `mtkloader/` — XNU started from `boot_a`, Android restored after each run
- `kernel/bsd/dev/redwood_emmc.c` — eMMC root read from an `xnusys` partition
  carved out of `userdata`
- `kernel/bsd/dev/redwood_mali.c` + `kernel/iokit/Kernel/RedwoodMali.cpp` —
  Mali-G52 with Mesa Panfrost and a Metal driver for CoreAnimation
- `kernel/bsd/dev/redwood_tcm.c` — touch (OmniVision TD4160 over SPI)
- `kernel/bsd/dev/redwood_mtkkeys.c` — power and volume buttons
- `kernel/bsd/dev/redwood_connsys.c` — Wi-Fi/Bluetooth (in progress)

Other useful references: [`Yousef13710/IOS-for-Merlinx`](https://github.com/Yousef13710/IOS-for-Merlinx)
(MT6768), [`RichkovGit/hakios-lancelot`](https://github.com/RichkovGit/hakios-lancelot)
(MT6768), and upstream `dipa-studio/ios-sweet` for the generic patches/root tooling.

## Milestones, in order

1. **Collect device facts** — run `tools/xpad20-preflight.sh` (read-only, needs
   `adb` + USB debugging): exact model/build, bootloader state, CPU ABI,
   partitions, GPU properties, and a copy of `/sys/firmware/fdt`. Obtain the
   Infinix/MediaTek kernel source for that exact build.
2. **Boot path** — unlock the bootloader (user's decision), back up unique
   partitions, study the `boot_a` layout, and adapt `mtkloader` so a tiny loader
   visibly writes to the framebuffer before XNU is attempted.
3. **Log + framebuffer** — find the continuous splash buffer, put the console
   there and keep a persistent log readable from Android.
4. **ADT and first XNU boot** — RAM banks, GIC, timer frequency, CPU IDs, MSDC
   node. Success looks like `waiting for root device`.
5. **Storage + iOS root** — port the MTK eMMC driver, choose a partition for
   the HFS root (`xnusys`-style carving is proven on MT6768), build the iPhone X
   root image. Success looks like launchd and the Apple logo.
6. **Identity, 1200×1920 screen, touch, buttons, battery** — iPhone X identity
   in the ADT, scale the panel, port the tablet's touch/PMIC drivers.
7. **GPU acceleration + optimization** — bring up Mali-G52 `GPU_ID` from the
   device, port Panfrost/EAGL/Metal, then optimize waits and cache sync. Do not
   call it accelerated until frames visibly render through the GPU.
8. **Optional extras** — Wi-Fi, Bluetooth, sound, camera.

## What can and cannot be done from this PC

- **Can:** edit code, prepare patches, build with GitHub Actions, run QEMU smoke
  tests, prepare boot/root images, and analyze device-tree dumps.
- **Cannot:** boot or install anything on the XPad 20 from here. No tablet is
  connected, `adb` is not installed, and any install needs an unlocked
  bootloader, a full backup, and explicit user confirmation before each write.
  **No install date can be promised** — this is step 1 of a hardware port.

## What is needed from the tablet owner

- Exact model and Android build (`Settings → About tablet`).
- Is OEM unlocking enabled / bootloader unlocked? (Do **not** unlock before a
  backup and a tested loader exist.)
- USB debugging enabled, tablet connected to this PC, permission to run the
  read-only preflight script.
- Infinix/MediaTek kernel source link for the exact firmware build.
- Explicit permission before any partition backup, `boot_a` write, or root-image
  write. Installing iOS into a data partition will erase Android data.

## Safety

No flashing, unlocking, formatting or partition writes will be done without
explicit, step-by-step confirmation. All tools here are read-only and host-side.
