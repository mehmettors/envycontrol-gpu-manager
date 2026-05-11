import subprocess
import re
import os
from dataclasses import dataclass
from typing import Optional

VENDOR_MAP = {
    "0x10de": ("NVIDIA", "NVIDIA Corporation"),
    "0x8086": ("Intel", "Intel Corporation"),
    "0x1002": ("AMD", "Advanced Micro Devices"),
    "0x1a03": ("ASpeed", "ASpeed Technology"),
}


@dataclass
class GPUInfo:
    vendor_id: str
    vendor: str
    vendor_long: str
    name: str = ""
    temp: Optional[int] = None
    utilization: Optional[str] = None
    is_active: bool = False
    power_state: str = "unknown"


def _nvidia_module_exists():
    try:
        r = subprocess.run(
            ["modinfo", "nvidia"], capture_output=True, text=True, timeout=3
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _nvidia_smi_available():
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=count", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def detect_gpus():
    gpus = []
    seen_vendors = set()

    drm_path = "/sys/class/drm"
    if os.path.exists(drm_path):
        for entry in sorted(os.listdir(drm_path)):
            m = re.match(r"^card(\d+)$", entry)
            if not m:
                continue
            vendor_file = os.path.join(drm_path, entry, "device", "vendor")
            if not os.path.exists(vendor_file):
                continue
            try:
                with open(vendor_file) as f:
                    vendor_id = f.read().strip()
            except (OSError, IOError):
                continue
            if vendor_id in seen_vendors:
                continue
            seen_vendors.add(vendor_id)

            vendor_info = VENDOR_MAP.get(vendor_id, ("Unknown", "Unknown Device"))
            gpu = GPUInfo(
                vendor_id=vendor_id,
                vendor=vendor_info[0],
                vendor_long=vendor_info[1],
                name=vendor_info[1],
                power_state="active",
            )
            gpus.append(gpu)

    for gpu in gpus:
        if gpu.vendor == "NVIDIA":
            _enrich_nvidia(gpu)
        elif gpu.vendor == "Intel":
            _enrich_intel(gpu)
        elif gpu.vendor == "AMD":
            _enrich_amd(gpu)
        _get_temp_from_hwmon(gpu)

    nvidia_in_drm = any(g.vendor == "NVIDIA" for g in gpus)
    if not nvidia_in_drm:
        if _nvidia_smi_available():
            dummy = GPUInfo(
                vendor_id="0x10de",
                vendor="NVIDIA",
                vendor_long="NVIDIA Corporation",
                name="NVIDIA GPU",
                power_state="active",
            )
            _enrich_nvidia(dummy)
            if dummy.name == "NVIDIA GPU":
                dummy.power_state = "offline"
            gpus.append(dummy)
        elif _nvidia_module_exists():
            gpus.append(
                GPUInfo(
                    vendor_id="0x10de",
                    vendor="NVIDIA",
                    vendor_long="NVIDIA Corporation",
                    name="NVIDIA GPU",
                    power_state="offline",
                )
            )

    intel_in_drm = any(g.vendor == "Intel" for g in gpus)
    if not intel_in_drm:
        _add_offline_pci_gpu(gpus, seen_vendors, "0x8086", "Intel")

    amd_in_drm = any(g.vendor == "AMD" for g in gpus)
    if not amd_in_drm:
        _add_offline_pci_gpu(gpus, seen_vendors, "0x1002", "AMD")

    return gpus


def _add_offline_pci_gpu(gpus, seen_vendors, target_vendor_id, vendor_name):
    pci_path = "/sys/bus/pci/devices"
    if not os.path.exists(pci_path):
        return
    for entry in os.listdir(pci_path):
        vendor_file = os.path.join(pci_path, entry, "vendor")
        class_file = os.path.join(pci_path, entry, "class")
        if not os.path.exists(vendor_file) or not os.path.exists(class_file):
            continue
        try:
            with open(vendor_file) as f:
                vid = f.read().strip()
            with open(class_file) as f:
                cls = f.read().strip()
        except (OSError, IOError):
            continue
        if vid != target_vendor_id:
            continue
        if not cls.startswith("0x03"):
            continue
        if vid in seen_vendors:
            return
        seen_vendors.add(vid)
        vendor_info = VENDOR_MAP.get(vid, (vendor_name, f"{vendor_name} Device"))
        gpu = GPUInfo(
            vendor_id=vid,
            vendor=vendor_info[0],
            vendor_long=vendor_info[1],
            name=vendor_info[1],
            power_state="offline",
        )
        gpus.append(gpu)
        return


def _enrich_nvidia(gpu):
    try:
        r = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,temperature.gpu,utilization.gpu",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            parts = [p.strip() for p in r.stdout.strip().split(", ")]
            if len(parts) >= 1 and parts[0]:
                gpu.name = parts[0]
            if len(parts) >= 2 and parts[1]:
                try:
                    gpu.temp = int(parts[1])
                except ValueError:
                    pass
            if len(parts) >= 3 and parts[2]:
                gpu.utilization = parts[2]
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass


def _enrich_intel(gpu):
    try:
        r = subprocess.run(
            ["glxinfo", "-B"], capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0:
            m = re.search(r"Device:\s*(.+)", r.stdout)
            if m:
                name = m.group(1).strip()
                if name:
                    gpu.name = name
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass


def _enrich_amd(gpu):
    try:
        r = subprocess.run(
            ["rocm-smi", "--showproductname", "--json"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            import json
            data = json.loads(r.stdout)
            for _, info in data.items():
                if "Card series" in info:
                    gpu.name = info["Card series"]
                    break
    except (
        subprocess.TimeoutExpired,
        FileNotFoundError,
        ImportError,
        ValueError,
    ):
        pass


def _get_temp_from_hwmon(gpu):
    if gpu.temp is not None:
        return
    hwmon_path = "/sys/class/hwmon"
    if not os.path.exists(hwmon_path):
        return
    for hwmon in os.listdir(hwmon_path):
        name_file = os.path.join(hwmon_path, hwmon, "name")
        if not os.path.exists(name_file):
            continue
        try:
            with open(name_file) as f:
                name = f.read().strip()
        except (OSError, IOError):
            continue
        if gpu.vendor.lower() not in name.lower():
            continue
        for entry in os.listdir(os.path.join(hwmon_path, hwmon)):
            m = re.match(r"temp(\d+)_input", entry)
            if not m:
                continue
            try:
                with open(os.path.join(hwmon_path, hwmon, entry)) as f:
                    raw = f.read().strip()
                gpu.temp = int(raw) // 1000
                return
            except (OSError, IOError, ValueError):
                continue


def get_current_opengl_renderer():
    try:
        r = subprocess.run(
            ["glxinfo"], capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0:
            m = re.search(r"OpenGL renderer string:\s*(.+)", r.stdout)
            if m:
                return m.group(1).strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return "Unknown"


def get_glx_renderer_for_gpu(vendor):
    env = {}
    if vendor == "NVIDIA":
        env["__NV_PRIME_RENDER_OFFLOAD"] = "1"
    elif vendor == "Intel":
        env["DRI_PRIME"] = "1"
    else:
        return None
    try:
        r = subprocess.run(
            ["glxinfo"],
            capture_output=True,
            text=True,
            timeout=5,
            env={**os.environ, **env},
        )
        if r.returncode == 0:
            m = re.search(r"OpenGL renderer string:\s*(.+)", r.stdout)
            if m:
                return m.group(1).strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def get_current_mode():
    try:
        r = subprocess.run(
            ["envycontrol", "--query"], capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return "unknown"
