#!/usr/bin/env python3
"""
Cross-Platform Environment Setup & Hardware Acceleration Installer for Bio-Research.
Detects OS, CPU architecture, and GPU acceleration (NVIDIA CUDA / Apple MPS / CPU),
and installs appropriate dependencies via uv, conda, or pip.

Usage:
    python scripts/setup_env.py               # Interactive setup & install
    python scripts/setup_env.py --check-only  # Run hardware & dependency check without installing
    python scripts/setup_env.py --cpu         # Force CPU-only PyTorch build
    python scripts/setup_env.py --cuda        # Force CUDA-enabled PyTorch build
"""

import os
import sys
import platform
import shutil
import subprocess
import argparse
from typing import Dict, Any, Tuple, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def print_banner():
    print("=" * 75)
    print(" [Bio-Research Plugin] One-Click Environment Initializer")
    print("=" * 75)


def check_python_version() -> Tuple[bool, str]:
    v = sys.version_info
    ver_str = f"{v.major}.{v.minor}.{v.micro}"
    if v.major < 3 or (v.major == 3 and v.minor < 10):
        return False, f"Python {ver_str} detected (Requires Python >= 3.10)"
    return True, f"Python {ver_str}"


def detect_hardware_acceleration() -> Dict[str, Any]:
    """Detect GPU hardware: NVIDIA CUDA, Apple Silicon MPS, or CPU-only."""
    hw_info = {
        "os": platform.system(),
        "arch": platform.machine(),
        "gpu_type": "CPU",
        "gpu_name": "None",
        "torch_index_url": "https://download.pytorch.org/whl/cpu",
        "details": ""
    }
    
    # 1. Check Apple Silicon MPS
    if platform.system() == "Darwin" and platform.machine() in ("arm64", "aarch64"):
        hw_info["gpu_type"] = "Apple Silicon (MPS)"
        hw_info["gpu_name"] = "Apple Metal Performance Shaders"
        hw_info["torch_index_url"] = ""  # Standard PyTorch on macOS arm64 supports MPS natively
        hw_info["details"] = "MPS GPU acceleration enabled for scvi-tools & PyTorch."
        return hw_info
    
    # 2. Check NVIDIA GPU via nvidia-smi
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        try:
            res = subprocess.run(
                [nvidia_smi, "--query-gpu=gpu_name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            if res.returncode == 0 and res.stdout.strip():
                lines = res.stdout.strip().splitlines()
                first_gpu = lines[0].split(",")
                gpu_name = first_gpu[0].strip()
                gpu_mem = first_gpu[1].strip() if len(first_gpu) > 1 else "?"
                
                hw_info["gpu_type"] = "NVIDIA CUDA"
                hw_info["gpu_name"] = f"{gpu_name} ({gpu_mem} MB VRAM)"
                hw_info["torch_index_url"] = "https://download.pytorch.org/whl/cu121"
                hw_info["details"] = f"Detected CUDA GPU ({gpu_name}). CUDA 12.x PyTorch build recommended."
                return hw_info
        except Exception:
            pass
    
    # 3. Fallback CPU
    hw_info["gpu_type"] = "CPU Only"
    hw_info["gpu_name"] = f"Host CPU ({platform.machine()})"
    hw_info["torch_index_url"] = "https://download.pytorch.org/whl/cpu"
    hw_info["details"] = "No discrete CUDA/MPS GPU detected. Installing lightweight CPU PyTorch."
    return hw_info


def detect_package_managers() -> Dict[str, Optional[str]]:
    """Detect available package managers (uv, conda, pip)."""
    return {
        "uv": shutil.which("uv"),
        "conda": shutil.which("conda") or shutil.which("mamba") or shutil.which("micromamba"),
        "pip": shutil.which("pip") or sys.executable
    }


def check_bio_toolchain() -> Dict[str, Tuple[bool, str]]:
    """Check external bioinformatics tools (Nextflow, Java, Docker, WSL2)."""
    results = {}
    
    # Java check
    java_cmd = shutil.which("java")
    if java_cmd:
        try:
            res = subprocess.run(["java", "-version"], capture_output=True, text=True, timeout=5)
            err_out = res.stderr or res.stdout
            results["Java"] = (True, "Installed")
        except Exception:
            results["Java"] = (False, "Installed but execution failed")
    else:
        results["Java"] = (False, "Not found (Required for Nextflow, OpenJDK 11+ recommended)")
    
    # Nextflow check
    nf_cmd = shutil.which("nextflow")
    if nf_cmd:
        results["Nextflow"] = (True, f"Installed ({nf_cmd})")
    else:
        results["Nextflow"] = (False, "Not found (Optional, needed for nf-core pipelines)")
    
    # Docker / Container check
    docker_cmd = shutil.which("docker")
    if docker_cmd:
        results["Docker"] = (True, "Installed")
    else:
        results["Docker"] = (False, "Not found (Optional, needed for containerized Nextflow pipelines)")
    
    # Windows WSL2 check
    if platform.system() == "Windows":
        wsl_cmd = shutil.which("wsl")
        if wsl_cmd:
            results["WSL2"] = (True, "Installed (Recommended for running Linux Nextflow containers on Windows)")
        else:
            results["WSL2"] = (False, "Not found")
            
    return results


def run_installation(hw_info: Dict[str, Any], mgrs: Dict[str, Optional[str]], root_dir: str):
    """Execute dependency installation."""
    req_file = os.path.join(root_dir, "requirements.txt")
    if not os.path.exists(req_file):
        print(f"Error: requirements.txt not found at {req_file}", file=sys.stderr)
        return False
    
    print("\nStarting Installation...")
    
    # Step 1: Install PyTorch with appropriate hardware build
    print("\n[Step 1/2] Installing PyTorch with optimal hardware acceleration...")
    torch_url = hw_info["torch_index_url"]
    
    if mgrs["uv"]:
        print("Using high-speed package manager 'uv'...")
        if torch_url:
            cmd = ["uv", "pip", "install", "torch>=2.0.0", "--index-url", torch_url]
        else:
            cmd = ["uv", "pip", "install", "torch>=2.0.0"]
        subprocess.run(cmd, check=True)
        
        # Step 2: Install remaining requirements
        print("\n[Step 2/2] Installing Bio-Research requirements (scanpy, scvi-tools, allotropy, etc.)...")
        subprocess.run(["uv", "pip", "install", "-r", req_file], check=True)
        
    else:
        print("Using standard 'pip'...")
        python_exe = sys.executable
        if torch_url:
            cmd = [python_exe, "-m", "pip", "install", "torch>=2.0.0", "--index-url", torch_url]
        else:
            cmd = [python_exe, "-m", "pip", "install", "torch>=2.0.0"]
        subprocess.run(cmd, check=True)
        
        # Step 2: Install remaining requirements
        print("\n[Step 2/2] Installing Bio-Research requirements (scanpy, scvi-tools, allotropy, etc.)...")
        subprocess.run([python_exe, "-m", "pip", "install", "-r", req_file], check=True)
    
    print("\n" + "=" * 75)
    print(" [DONE] Bio-Research environment setup completed successfully!")
    print("=" * 75)
    return True


def main():
    parser = argparse.ArgumentParser(description="Bio-Research Environment Initializer")
    parser.add_argument("--check-only", action="store_true", help="Run system check without installing")
    parser.add_argument("--cpu", action="store_true", help="Force CPU-only PyTorch installation")
    parser.add_argument("--cuda", action="store_true", help="Force CUDA PyTorch installation")
    args = parser.parse_args()
    
    print_banner()
    
    # 1. Python Check
    py_ok, py_msg = check_python_version()
    status_icon = "[OK]" if py_ok else "[FAIL]"
    print(f"Python Version   : {py_msg} {status_icon}")
    if not py_ok:
        sys.exit(1)
    
    # 2. Hardware Acceleration Check
    hw = detect_hardware_acceleration()
    if args.cpu:
        hw["gpu_type"] = "CPU (Forced)"
        hw["torch_index_url"] = "https://download.pytorch.org/whl/cpu"
    elif args.cuda:
        hw["gpu_type"] = "NVIDIA CUDA (Forced)"
        hw["torch_index_url"] = "https://download.pytorch.org/whl/cu121"
        
    print(f"Acceleration     : {hw['gpu_type']} -- {hw['gpu_name']}")
    print(f"Details          : {hw['details']}")
    
    # 3. Package Managers
    mgrs = detect_package_managers()
    preferred_mgr = "uv (High speed)" if mgrs["uv"] else ("conda" if mgrs["conda"] else "pip")
    print(f"Package Manager  : Preferred -> {preferred_mgr}")
    
    # 4. Bioinformatics Toolchain
    tools = check_bio_toolchain()
    print("\nBioinformatics External Toolchain:")
    for t_name, (t_ok, t_msg) in tools.items():
        icon = "[OK]" if t_ok else "[--]"
        print(f"   - {t_name:<10}: {icon} {t_msg}")
    
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    if args.check_only:
        print("\n[Check-Only Mode] Pre-flight system check completed.")
        return
    
    run_installation(hw, mgrs, root_dir)


if __name__ == "__main__":
    main()
