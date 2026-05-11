import subprocess

SWITCH_MODES = ["integrated", "hybrid", "nvidia"]


def query_mode():
    try:
        r = subprocess.run(
            ["envycontrol", "--query"], capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return "unknown"


def detect_display_manager():
    try:
        r = subprocess.run(
            ["systemctl", "status", "display-manager"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if r.returncode == 0:
            for dm in ["sddm", "gdm", "gdm3", "lightdm"]:
                if dm in r.stdout.lower():
                    return dm
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    try:
        r = subprocess.run(["ps", "-e"], capture_output=True, text=True, timeout=3)
        for dm in ["sddm", "gdm", "gdm3", "lightdm"]:
            if dm in r.stdout.lower():
                return dm
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def switch_mode(mode):
    if mode not in SWITCH_MODES:
        return False, f"Invalid mode: {mode}"

    args = ["pkexec", "envycontrol", "--switch", mode]

    if mode == "nvidia":
        dm = detect_display_manager()
        if dm:
            args.extend(["--dm", dm])

    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=120)
        if r.returncode == 0:
            return True, r.stdout.strip()
        else:
            err = r.stderr.strip() or r.stdout.strip() or f"Exit code: {r.returncode}"
            return False, err
    except subprocess.TimeoutExpired:
        return False, "Operation timed out"
    except FileNotFoundError:
        return (
            False,
            "pkexec not found. Install polkit: sudo apt install policykit-1",
        )
