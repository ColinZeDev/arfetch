from concurrent.futures import ThreadPoolExecutor
import subprocess
import platform
import argparse
import shutil
import glob
import yaml
import os

VERSION = "0.0.1-a" # a for alpha duhh

parser = argparse.ArgumentParser(prog="arfetch", add_help=True)
parser.add_argument("-v", "--version", action="version", version=f"arfetch {VERSION}")
parser.parse_args()

if platform.system().lower() != "linux":
    raise OSError("Must be on GNU/Linux")

def _read_os_release() -> dict:
    try:
        with open("/etc/os-release") as f:
            return {
                k: v.strip('"')
                for line in f if "=" in line
                for k, v in [line.strip().split("=", 1)]
            }
    except FileNotFoundError:
        return {}

OS_RELEASE = _read_os_release()

if OS_RELEASE.get("PRETTY_NAME", platform.system()).lower() != "artix linux":
    print("Ur not on Artix, this script is only for Artix users")

config_dir  = os.path.expanduser("~/.config/arfetch")
config_file = os.path.join(config_dir, "config.yml")

if not os.path.exists(config_dir):
    os.makedirs(config_dir, exist_ok=True)
    with open(config_file, 'w') as f:
        f.write("""\
# arfetch configuration file (auto generated)

Main:
    clrs:
        maincolor: "38;2;239;132;33"
        secondarycolor: "38;2;142;56;217"
""")

with open(config_file, 'r') as f:
    d = yaml.safe_load(f)
    MAINCOLOR      = f"\033[{d['Main']['clrs']['maincolor']}m"
    SECONDARYCOLOR = f"\033[{d['Main']['clrs']['secondarycolor']}m"

SKIP_FSTYPES = {"devtmpfs", "tmpfs", "devpts", "sysfs", "proc", "cgroup", "vfat", "swap"}

INIT_SYSTEMS = {
    "openrc": "OpenRC",
    "runit": "runit",
    "s6-svscan": "s6",
    "dinit": "Dinit",
}

LOGO = [
    r"    ",
    r"    ",
    r"      /\ ",
    r"     /  \ ",
    r"    /`'.,\ ",
    r"   /     ',",
    r"  /      ,`\ ",
    r" /   ,.'`.  \ ",
    r"/.,'`     `'.\ ",
    r"    ",
]

RESET   = "\033[0m"
BOLD    = "\033[1m"
LABELS  = ["Host", "OS", "Kernel", "Init", "Shell", "CPU", "GPU", "RAM", "Disk", "Uptime"]
MAX_LEN = max(len(l) for l in LABELS)


class InfoGrab:
    def __init__(self) -> None:
        self._init = None
        self._clr  = None

    def clr(self) -> str:
        if self._clr:
            return self._clr
        line = next((l for l in OS_RELEASE if "ANSI_COLOR" in l), None)
        if line:
            code = OS_RELEASE.get("ANSI_COLOR", "")
            if code:
                self._clr = f"{BOLD}\033[{code}m"
                return self._clr
        self._clr = RESET
        return self._clr

    def logo_lines(self) -> list[str]:
        return [f"{self.clr()}{l}{RESET}" for l in LOGO]

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
                r = subprocess.run(["rc-status", "--all", "--nocolor"],
                                   capture_output=True, text=True, timeout=3)
                return str(r.stdout.count("started"))
            elif init == "runit":
                active = sum(
                    1 for svc in glob.glob("/var/service/*")
                    if subprocess.run(["sv", "status", svc],
                                      capture_output=True, text=True,
                                      timeout=2).stdout.startswith("run:")
                )
                return str(active)
            elif init == "s6":
                services = glob.glob("/run/s6/legacy-services/*") or glob.glob("/service/*")
                return str(len(services))
            elif init == "Dinit":
                r = subprocess.run(["dinitctl", "list"],
                                   capture_output=True, text=True, timeout=3)
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
        cores   = 0
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
            r = subprocess.run(["lspci", "-mm", "-d", "::0300"],
                               capture_output=True, text=True, timeout=3)
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
            info = {}
            with open("/proc/meminfo") as f:
                for line in f:
                    k, v = line.split(":", 1)
                    info[k.strip()] = int(v.split()[0])
            total = info["MemTotal"] // 1024
            used  = (info["MemTotal"] - info["MemAvailable"]) // 1024
            return f"{used} MB / {total} MB"
        except Exception:
            return "Unknown"

    @staticmethod
    def get_disks() -> list[dict]:
        disks = []
        try:
            with open("/proc/mounts") as f:
                mounts = [line.split() for line in f if len(line.split()) >= 6]
            seen = set()
            for parts in mounts:
                device, mountpoint, fstype = parts[0], parts[1], parts[2]
                if not device.startswith("/dev/"):
                    continue
                if fstype in SKIP_FSTYPES or device in seen:
                    continue
                seen.add(device)
                usage = shutil.disk_usage(mountpoint)
                disks.append({
                    "device":     device,
                    "mountpoint": mountpoint,
                    "fstype":     fstype,
                    "used":       usage.used,
                    "total":      usage.total,
                })
        except Exception:
            pass
        return disks

    @staticmethod
    def fmt_gib(n: int) -> str:
        return f"{n / (1024 ** 3):.2f} GiB"

    def get_disk_lines(self) -> list[str]:
        disks = self.get_disks()
        multi = len(disks) > 1
        lines = []
        for i, d in enumerate(disks, 1):
            label = f"Disk {i}" if multi else "Disk"
            lines.append(
                f"{label} [{d['device']}]: "
                f"{self.fmt_gib(d['used'])} / {self.fmt_gib(d['total'])} "
                f"({d['fstype']})"
            )
        return lines or ["Unknown"]

    @staticmethod
    def get_shell_version() -> str:
        shell = os.environ.get("SHELL", "")
        if not shell:
            return "unknown"
        try:
            r = subprocess.run([shell, "--version"], capture_output=True, text=True, timeout=3)
            output = r.stdout.splitlines()[0]  # first line has the version

            # zsh:  "zsh 5.9 (x86_64-pc-linux-gnu)"
            # bash: "GNU bash, version 5.2.21(1)-release ..."
            # fish: "fish, version 3.7.0"

            for part in output.split():
                if part[0].isdigit():
                    return part.split("(")[0]  # strip trailing (1) etc
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
                "services":  executor.submit(self.get_active_services),
                "cpu":       executor.submit(self.get_cpu),
                "counts":    executor.submit(self.get_cpu_counts),
                "gpu":       executor.submit(self.get_gpu),
                "ram":       executor.submit(self.get_ram),
                "disks":     executor.submit(self.get_disk_lines),
                "uptime":    executor.submit(self.get_uptime),
                "os":        executor.submit(self.get_os_info),
                "shell_ver": executor.submit(self.get_shell_version),
            }
            results = {k: v.result() for k, v in futures.items()}

        cores, threads = results["counts"]
        disk_lines     = results["disks"]
        logo_raw       = LOGO
        logo_colored   = self.logo_lines()
        shell = os.path.basename(os.environ.get("SHELL", "unknown"))

        def label(name: str) -> str:
            return f"{BOLD}{MAINCOLOR}{name + ':':<{MAX_LEN + 3}}{RESET}"

        info = [
            f"{label('OS')} {results['os']} ({uname.machine})",
            f"{label('Kernel')} {uname.release}",
            f"{label('Init')} {self.detect_init()} ({results['services']} active services)",
            f"{label('Shell')} {shell} {results['shell_ver']}",
            f"{label('CPU')} {results['cpu']} ({cores}c / {threads}t)",
            f"{label('GPU')} {results['gpu']}",
            f"{label('RAM')} {results['ram']}",
            f"{label('Disk')} {disk_lines[0]}",
            *[f"{' ' * (MAX_LEN + 2)}{d}" for d in disk_lines[1:]],
            f"{label('Uptime')} {results['uptime']}",
        ]

        user = f"  {BOLD}{MAINCOLOR}{os.environ['USER']}{RESET}@{BOLD}{MAINCOLOR}{platform.node()}{RESET}"
        sep  = f"  {BOLD}{SECONDARYCOLOR}+------------------------------------------+\033[0m"
        rows = [f"  | {row}" for row in info]
        box  = [user] + [sep] + rows + [sep]

        logo_w = max(len(l) for l in logo_raw)
        total  = max(len(logo_colored), len(box))
        logo_colored += [""] * (total - len(logo_colored))
        box          += [""] * (total - len(box))

        lines = [
            f"{colored:<{logo_w + len(colored) - len(raw)}}{b}"
            for colored, raw, b in zip(
                logo_colored,
                logo_raw + [""] * (total - len(logo_raw)),
                box
            )
        ]

        return "\n" + "\n".join(lines) + "\n"


if __name__ == "__main__":
    g = InfoGrab()
    print(g.build())