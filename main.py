from concurrent.futures import ThreadPoolExecutor
import subprocess
import platform
import argparse
import shutil
import yaml
import glob
import os

VERSION = "0.0.2-a"  # a for alpha duh

parser = argparse.ArgumentParser(prog="arfetch", add_help=True)
parser.add_argument(
    "-v",
    "--version",
    action="version",
    version=f"ArFetch - Artix Linux Fetch\nCurrently on version v{VERSION}",
)
parser.parse_args()

if platform.system().lower() != "linux":
    raise OSError("Must be on GNU/Linux")


def _read_os_release() -> dict:
    try:
        with open("/etc/os-release") as f:
            return {
                k: v.strip('"')
                for line in f
                if "=" in line
                for k, v in [line.strip().split("=", 1)]
            }
    except FileNotFoundError:
        return {}


OS_RELEASE = _read_os_release()

if OS_RELEASE.get("PRETTY_NAME", "").lower() != "artix linux":
    print("Ur not on Artix, this script is only for Artix users")


# ── Config ────────────────────────────────────────────────────────────────────

config_dir = os.path.expanduser("~/.config/arfetch")
config_file = os.path.join(config_dir, "config.yml")

if not os.path.exists(config_dir):
    os.makedirs(config_dir, exist_ok=True)
    with open(config_file, "w") as f:
        f.write("""\
# arfetch configuration file (auto generated)

Main:
    clrs:
        maincolor: "38;5;45"
        secondarycolor: "38;5;26"
""")

with open(config_file, "r") as cfg_file:
    _cfg = yaml.safe_load(cfg_file)
    MAINCOLOR = f"\033[{_cfg['Main']['clrs']['maincolor']}m"
    SECONDARYCOLOR = f"\033[{_cfg['Main']['clrs']['secondarycolor']}m"

INFO_ICON_WIDTH = 2
INFO_GAP = "  "

SKIP_FSTYPES = {
    "devtmpfs",
    "tmpfs",
    "devpts",
    "sysfs",
    "proc",
    "cgroup",
    "vfat",
    "swap",
}

INIT_SYSTEMS = {
    "openrc": "OpenRC",
    "runit": "runit",
    "s6-svscan": "s6",
    "dinit": "Dinit",
}

LOGO = [
    r"           '           ",
    r"          'A'          ",
    r"         'ooo'         ",
    r"        'ookxo'        ",
    r"        `ookxxo'       ",
    r"      '.   `ooko'      ",
    r"     'ooo`.   `oo'     ",
    r"    'ooxxxoo`.   `'    ",
    r"   'ookxxxkooo.`   .   ",
    r"  'ookxxkoo'`   .'oo'  ",
    r" 'ooxoo'`     .:ooxxo' ",
    r"'io'`             `'oo'",
    r"'`                     ",
]

RESET = "\033[0m"
BOLD = "\033[1m"

LABELS = ["OS", "Kernel", "Init", "Shell", "CPU", "GPU", "RAM", "Disk", "Uptime"]
MAX_LEN = max(len(l) for l in LABELS)


def surrogate_pair_to_codepoint(high: int, low: int) -> str:
    if not (0xD800 <= high <= 0xDBFF):
        raise ValueError(f"Invalid high surrogate: {hex(high)}")
    if not (0xDC00 <= low <= 0xDFFF):
        raise ValueError(f"Invalid low surrogate: {hex(low)}")
    return chr(0x10000 + (high - 0xD800) * 0x400 + (low - 0xDC00))


class InfoGrab:
    def __init__(self) -> None:
        self._init: str | None = None
        self._clr: str | None = None

    def clr(self) -> str:
        if self._clr:
            return self._clr
        code = OS_RELEASE.get("ANSI_COLOR", "")
        self._clr = f"{BOLD}\033[{code}m" if code else RESET
        return self._clr

    def logo_lines(self) -> list[str]:
        FRAME = set("'`.,i")
        FILL = set("oxk")

        def color_char(c: str) -> str:
            if c == "A":
                return f"{BOLD}{MAINCOLOR}{c}{RESET}"
            elif c == ":":
                return f"{BOLD}{MAINCOLOR}{c}{RESET}"
            elif c == "i":
                return f"{BOLD}{MAINCOLOR}{c}{RESET}"
            elif c in FRAME:
                return f"{BOLD}{SECONDARYCOLOR}{c}{RESET}"
            elif c in FILL:
                return f"{BOLD}{MAINCOLOR}{c}{RESET}"
            return c

        return ["".join(color_char(c) for c in line) for line in LOGO]

    def detect_init(self) -> str:
        if self._init:
            return self._init
        for binary, name in INIT_SYSTEMS.items():
            if shutil.which(binary):
                self._init = name
                return name
        self._init = "Unknown"
        return "Unknown"

    def get_active_services(self) -> str:
        init = self.detect_init()
        try:
            if init == "OpenRC":
                r = subprocess.run(
                    ["rc-status", "--all", "--nocolor"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                return str(r.stdout.count("started"))

            elif init == "runit":
                active = sum(
                    1
                    for svc in glob.glob("/var/service/*")
                    if subprocess.run(
                        ["sv", "status", svc],
                        capture_output=True,
                        text=True,
                        timeout=2,
                    ).stdout.startswith("run:")
                )
                return str(active)

            elif init == "s6":
                services = glob.glob("/run/s6/legacy-services/*") or glob.glob(
                    "/service/*"
                )
                return str(len(services))

            elif init == "Dinit":
                r = subprocess.run(
                    ["dinitctl", "list"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                return str(sum(1 for l in r.stdout.splitlines() if "[[+]]" in l))

        except Exception:
            pass
        return "?"

    @staticmethod
    def get_os_info() -> str:
        return OS_RELEASE.get("PRETTY_NAME", platform.system())

    @staticmethod
    def get_cpu() -> str:
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("model name"):
                        return line.split(":", 1)[1].strip()
        except Exception:
            pass
        return "Unknown"

    @staticmethod
    def get_cpu_counts() -> tuple[int, int]:
        cores = 0
        threads = len(os.sched_getaffinity(0))
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("cpu cores"):
                        cores = int(line.split(":", 1)[1].strip())
                        break
        except Exception:
            pass
        return cores, threads

    @staticmethod
    def get_gpu() -> str:
        try:
            for card in sorted(glob.glob("/sys/class/drm/card[0-9]/device/uevent")):
                with open(card) as f:
                    info = dict(l.strip().split("=", 1) for l in f if "=" in l)
                if info.get("PCI_CLASS", "")[:2] == "03":
                    label_path = card.replace("uevent", "label")
                    if os.path.exists(label_path):
                        with open(label_path) as f:
                            return f.read().strip()
        except Exception:
            pass
        try:
            r = subprocess.run(
                ["lspci", "-mm", "-d", "::0300"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            for line in r.stdout.splitlines():
                parts = line.split('"')
                if len(parts) >= 6:
                    return parts[5]
        except Exception:
            pass
        return "Unknown"

    @staticmethod
    def get_ram() -> str:
        try:
            mem: dict[str, int] = {}
            with open("/proc/meminfo") as f:
                for line in f:
                    k, v = line.split(":", 1)
                    mem[k.strip()] = int(v.split()[0])
            total = mem["MemTotal"] // 1024
            used = (mem["MemTotal"] - mem["MemAvailable"]) // 1024
            return f"{used} MB / {total} MB"
        except Exception:
            return "Unknown"

    @staticmethod
    def get_disks() -> list[dict]:
        disks: list[dict] = []
        try:
            with open("/proc/mounts") as f:
                mounts = [line.split() for line in f if len(line.split()) >= 6]
            seen: set[str] = set()
            for parts in mounts:
                device, mountpoint, fstype = parts[0], parts[1], parts[2]
                if not device.startswith("/dev/"):
                    continue
                if fstype in SKIP_FSTYPES or device in seen:
                    continue
                seen.add(device)
                usage = shutil.disk_usage(mountpoint)
                disks.append(
                    {
                        "device": device,
                        "mountpoint": mountpoint,
                        "fstype": fstype,
                        "used": usage.used,
                        "total": usage.total,
                    }
                )
        except Exception:
            pass
        return disks

    @staticmethod
    def fmt_gib(n: int) -> str:
        return f"{n / (1024**3):.2f} GiB"

    @staticmethod
    def get_desktop() -> str:
        processes = {
            "hyprland": "Hyprland",
            "sway": "Sway",
            "i3": "i3",
            "bspwm": "bspwm",
            "dwm": "DWM",
            "openbox": "Openbox",
            "kwin_wayland": "KDE",
            "kwin_x11": "KDE",
            "plasmashell": "KDE Plasma",
            "gnome-shell": "GNOME",
            "xfce4-session": "XFCE",
            "mate-session": "MATE",
            "cinnamon": "Cinnamon",
            "lxqt-session": "LXQt",
        }

        detected = None

        for proc, name in processes.items():
            try:
                r = subprocess.run(
                    ["pgrep", "-x", proc],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

                if r.returncode == 0:
                    detected = name
                    break

            except Exception:
                pass

        if not detected:
            detected = "Unknown"

        if os.environ.get("WAYLAND_DISPLAY"):
            display = "Wayland"
        elif os.environ.get("DISPLAY"):
            display = "X11"
        else:
            display = "Unknown"

        return f"{detected} ({display})"

    def get_disk_lines(self) -> list[str]:
        disk_list = self.get_disks()
        multi = len(disk_list) > 1
        lines = []
        for i, disk in enumerate(disk_list, 1):
            label = f"Disk {i}" if multi else "Disk"
            lines.append(
                f"{label} [{disk['device']}]: "
                f"{self.fmt_gib(disk['used'])} / {self.fmt_gib(disk['total'])} "
                f"({disk['fstype']})"
            )
        return lines or ["Unknown"]

    @staticmethod
    def get_shell_version() -> str:
        shell = os.environ.get("SHELL", "")
        if not shell:
            return "unknown"
        try:
            r = subprocess.run(
                [shell, "--version"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            # zsh:  "zsh 5.9 (x86_64-pc-linux-gnu)"
            # bash: "GNU bash, version 5.2.21(1)-release ..."
            # fish: "fish, version 3.7.0"
            for part in r.stdout.splitlines()[0].split():
                if part[0].isdigit():
                    return part.split("(")[0]
        except Exception:
            pass
        return "unknown"

    @staticmethod
    def get_uptime() -> str:
        try:
            with open("/proc/uptime") as f:
                seconds = float(f.read().split()[0])
            h, rem = divmod(int(seconds), 3600)
            return f"{h}h {rem // 60}m"
        except Exception:
            return "Unknown"

    def build(self) -> str:
        uname = platform.uname()

        with ThreadPoolExecutor(max_workers=9) as executor:
            futures = {
                "services": executor.submit(self.get_active_services),
                "cpu": executor.submit(self.get_cpu),
                "counts": executor.submit(self.get_cpu_counts),
                "gpu": executor.submit(self.get_gpu),
                "ram": executor.submit(self.get_ram),
                "disks": executor.submit(self.get_disk_lines),
                "uptime": executor.submit(self.get_uptime),
                "os": executor.submit(self.get_os_info),
                "shell_ver": executor.submit(self.get_shell_version),
                "desktop": executor.submit(self.get_desktop),
            }
            results = {k: v.result() for k, v in futures.items()}

        cores, threads = results["counts"]
        disk_lines = results["disks"]
        shell = os.path.basename(os.environ.get("SHELL", "unknown"))
        user = os.environ.get("USER") or os.getlogin()

        logo_raw = LOGO
        logo_colored = self.logo_lines()

        LABEL_WIDTH = MAX_LEN + 3

        def label(name: str) -> str:
            text = f"{name}:"
            padded = f"{text:<{LABEL_WIDTH}}"
            return f"{BOLD}{MAINCOLOR}{padded}{RESET}"

        def row(icon: str, key: str, value: str) -> str:
            return f"{icon:<{INFO_ICON_WIDTH}}{INFO_GAP}{label(key)}{value}"

        DISK_ICON = surrogate_pair_to_codepoint(0xDB80, 0xDECA)
        UPTIME_ICON = surrogate_pair_to_codepoint(0xDB80, 0xDF79)

        info = [
            row("\uf31f", "OS", f"{results['os']} ({uname.machine})"),
            row("\ue712", "Kernel", uname.release),
            row(
                "\uf013",
                "Init",
                f"{self.detect_init()} ({results['services']} active services)",
            ),
            row(
                "\ue795",
                "Shell",
                f"{shell} {results['shell_ver']}",
            ),
            row(
                "\uf108",
                "DE/WM",
                results["desktop"],
            ),
            row(
                "\uf4bc",
                "CPU",
                f"{results['cpu']} ({cores}c / {threads}t)",
            ),
            row(
                "\uf4bc",
                "GPU",
                results["gpu"],
            ),
            row(
                "\uefc5",
                "RAM",
                results["ram"],
            ),
            row(
                DISK_ICON,
                "Disk",
                disk_lines[0],
            ),
            *[" " * (MAX_LEN + 12) + d for d in disk_lines[1:]],
            row(
                UPTIME_ICON,
                "Uptime",
                results["uptime"],
            ),
        ]

        quote = f"  {BOLD}{MAINCOLOR}\uf1fc  The Art Of Linux{RESET}"
        header = f"  {BOLD}{MAINCOLOR}\uf007  {user}{RESET}@{BOLD}{MAINCOLOR}{platform.node()}{RESET}"
        sep = f"  {BOLD}{SECONDARYCOLOR}+------------------------------------------+{RESET}"
        box = [header, sep] + [f"  | {row}" for row in info] + [sep, quote]

        logo_w = max(len(l) for l in logo_raw) + 3
        total = max(len(logo_colored), len(box))
        logo_colored += [""] * (total - len(logo_colored))
        box += [""] * (total - len(box))

        lines = [
            f"{colored:<{logo_w + len(colored) - len(raw)}}{b}"
            for colored, raw, b in zip(
                logo_colored,
                logo_raw + [""] * (total - len(logo_raw)),
                box,
            )
        ]

        return "\n" + "\n".join(lines) + "\n"


if __name__ == "__main__":
    g = InfoGrab()
    print(g.build())
