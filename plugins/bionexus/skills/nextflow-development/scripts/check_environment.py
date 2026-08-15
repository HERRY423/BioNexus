#!/usr/bin/env python3
"""
Pre-flight environment validation for nf-core pipelines.

Checks Docker, Nextflow, Java, system resources, and network connectivity.
Run this BEFORE attempting any pipeline execution.

Supports Linux, macOS, and Windows.

Usage:
    python check_environment.py
    python check_environment.py --json
"""

import csv
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class CheckResult:
    """Result of a single environment check."""

    name: str
    passed: bool
    message: str
    details: Optional[str] = None
    fix: Optional[str] = None


@dataclass
class EnvironmentReport:
    """Complete environment validation report."""

    ready: bool
    checks: List[CheckResult] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self):
        return {
            "ready": self.ready,
            "checks": [asdict(c) for c in self.checks],
            "recommendations": self.recommendations,
        }


# ---- Platform helpers ----------------------------------------------------

_IS_WINDOWS = platform.system() == "Windows"
_IS_MACOS = platform.system() == "Darwin"
_IS_LINUX = platform.system() == "Linux"


def _get_memory_gb() -> float:
    """Return total system memory in GB (cross-platform)."""
    if _IS_LINUX:
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        return int(line.split()[1]) / (1024 * 1024)
        except (FileNotFoundError, PermissionError):
            pass
        return 0.0

    if _IS_MACOS:
        try:
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return int(result.stdout.strip()) / (1024**3)
        except Exception:
            pass
        return 0.0

    if _IS_WINDOWS:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return int(result.stdout.strip()) / (1024**3)
        except Exception:
            pass
        # Fallback: wmic
        try:
            result = subprocess.run(
                ["wmic", "computersystem", "get", "TotalPhysicalMemory"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            for line in result.stdout.strip().splitlines():
                val = line.strip()
                if val.isdigit():
                    return int(val) / (1024**3)
        except Exception:
            pass
        return 0.0

    return 0.0


def _get_disk_gb() -> float:
    """Return available disk space in GB for cwd (cross-platform)."""
    try:
        if _IS_WINDOWS:
            import ctypes

            free_bytes = ctypes.c_ulonglong(0)
            ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                ctypes.c_wchar_p(os.getcwd()),
                None,
                None,
                ctypes.pointer(free_bytes),
            )
            return free_bytes.value / (1024**3)
        else:
            statvfs = os.statvfs(".")
            return (statvfs.f_frsize * statvfs.f_bavail) / (1024**3)
    except Exception:
        return 0.0


# ---- Individual checks ---------------------------------------------------


def check_docker() -> CheckResult:
    if not shutil.which("docker"):
        return CheckResult(
            name="Docker",
            passed=False,
            message="Docker not found in PATH",
            fix="Install Docker: https://docs.docker.com/get-docker/",
        )

    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=15,
        )

        if result.returncode != 0:
            stderr_lower = result.stderr.lower()
            if "permission denied" in stderr_lower:
                return CheckResult(
                    name="Docker",
                    passed=False,
                    message="Docker permission denied",
                    details="Cannot connect to Docker daemon",
                    fix="sudo usermod -aG docker $USER && newgrp docker",
                )
            elif "cannot connect" in stderr_lower or "is the docker daemon running" in stderr_lower:
                return CheckResult(
                    name="Docker",
                    passed=False,
                    message="Docker daemon not running",
                    details=result.stderr[:200] if result.stderr else None,
                    fix=("Start Docker Desktop from the system tray" if _IS_WINDOWS else "sudo systemctl start docker"),
                )
            else:
                return CheckResult(
                    name="Docker",
                    passed=False,
                    message="Docker error",
                    details=result.stderr[:200] if result.stderr else None,
                    fix="Check Docker installation and daemon status",
                )

        return CheckResult(
            name="Docker",
            passed=True,
            message="Docker is available and running",
        )

    except subprocess.TimeoutExpired:
        return CheckResult(
            name="Docker",
            passed=False,
            message="Docker command timed out",
            fix=(
                "Check Docker Desktop status"
                if _IS_WINDOWS
                else "Check Docker daemon status: sudo systemctl status docker"
            ),
        )
    except Exception as e:
        return CheckResult(
            name="Docker",
            passed=False,
            message=f"Docker check failed: {str(e)}",
        )


def check_nextflow() -> CheckResult:
    if not shutil.which("nextflow"):
        return CheckResult(
            name="Nextflow",
            passed=False,
            message="Nextflow not found in PATH",
            fix="curl -s https://get.nextflow.io | bash && mv nextflow ~/bin/ && export PATH=$HOME/bin:$PATH",
        )

    try:
        result = subprocess.run(
            ["nextflow", "-version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout + result.stderr
        version_line = output.strip().split("\n")[0] if output else ""

        import re

        match = re.search(r"(\d+)\.(\d+)\.(\d+)", version_line)

        if match:
            major, minor, patch = int(match.group(1)), int(match.group(2)), int(match.group(3))
            version_str = f"{major}.{minor}.{patch}"

            if major > 23 or (major == 23 and minor >= 4):
                return CheckResult(
                    name="Nextflow",
                    passed=True,
                    message=f"Nextflow {version_str} installed",
                    details=version_line,
                )
            else:
                return CheckResult(
                    name="Nextflow",
                    passed=False,
                    message=f"Nextflow {version_str} is outdated (requires >= 23.04)",
                    details=version_line,
                    fix="nextflow self-update",
                )

        return CheckResult(
            name="Nextflow",
            passed=True,
            message="Nextflow installed (version unknown)",
            details=version_line,
        )

    except subprocess.TimeoutExpired:
        return CheckResult(
            name="Nextflow",
            passed=False,
            message="Nextflow command timed out",
            fix="Check Nextflow installation",
        )
    except Exception as e:
        return CheckResult(
            name="Nextflow",
            passed=False,
            message=f"Nextflow check failed: {str(e)}",
        )


def check_java() -> CheckResult:
    if not shutil.which("java"):
        fix_msg = "winget install Microsoft.OpenJDK.11" if _IS_WINDOWS else "sudo apt install openjdk-11-jdk"
        return CheckResult(
            name="Java",
            passed=False,
            message="Java not found in PATH",
            fix=f"Install Java 11+: {fix_msg}",
        )

    try:
        result = subprocess.run(
            ["java", "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = result.stderr or result.stdout
        import re

        match = re.search(r'version "(\d+)', output)

        if match:
            version = int(match.group(1))
            version_line = output.strip().split("\n")[0]

            if version >= 11:
                return CheckResult(
                    name="Java",
                    passed=True,
                    message=f"Java {version} installed",
                    details=version_line,
                )
            else:
                return CheckResult(
                    name="Java",
                    passed=False,
                    message=f"Java {version} is too old (requires >= 11)",
                    details=version_line,
                    fix="Install Java 11+: sudo apt install openjdk-11-jdk",
                )

        return CheckResult(
            name="Java",
            passed=True,
            message="Java installed",
            details=output.strip().split("\n")[0] if output else None,
        )

    except Exception as e:
        return CheckResult(
            name="Java",
            passed=False,
            message=f"Java check failed: {str(e)}",
        )


def check_resources() -> CheckResult:
    try:
        cpu_count = os.cpu_count() or 1
        mem_gb = _get_memory_gb()
        disk_gb = _get_disk_gb()

        details = (
            f"OS: {platform.system()} {platform.release()}, "
            f"CPUs: {cpu_count}, Memory: {mem_gb:.1f}GB, Disk: {disk_gb:.1f}GB available"
        )

        warnings = []
        if cpu_count < 4:
            warnings.append(f"Low CPU count ({cpu_count}). Consider --max_cpus {cpu_count}")
        if 0 < mem_gb < 8:
            warnings.append(f"Low memory ({mem_gb:.1f}GB). Use --max_memory '{int(mem_gb)}GB'")
        if 0 < disk_gb < 50:
            warnings.append(f"Low disk space ({disk_gb:.1f}GB). Pipelines need ~100GB for human data")

        if warnings:
            return CheckResult(
                name="Resources",
                passed=True,
                message="Resources available (with warnings)",
                details=details,
                fix="; ".join(warnings),
            )

        return CheckResult(
            name="Resources",
            passed=True,
            message="Sufficient resources available",
            details=details,
        )

    except Exception as e:
        return CheckResult(
            name="Resources",
            passed=True,
            message=f"Could not fully check resources: {str(e)}",
        )


def check_network() -> CheckResult:
    try:
        import urllib.request

        headers = {"User-Agent": "nf-core-helper/1.0"}

        def _reachable(url):
            try:
                req = urllib.request.Request(url, headers=headers)
                urllib.request.urlopen(req, timeout=10)
                return True
            except Exception:
                return False

        docker_hub_ok = _reachable("https://hub.docker.com")
        nfcore_ok = _reachable("https://nf-co.re")

        if docker_hub_ok and nfcore_ok:
            return CheckResult(
                name="Network",
                passed=True,
                message="Network connectivity OK (Docker Hub & nf-core reachable)",
            )
        elif docker_hub_ok:
            return CheckResult(
                name="Network",
                passed=True,
                message="Docker Hub reachable (nf-core.re not reachable)",
                details="Pipeline downloads may still work via GitHub",
            )
        else:
            return CheckResult(
                name="Network",
                passed=False,
                message="Cannot reach Docker Hub",
                fix="Check network connection. Containers require Docker Hub access.",
            )

    except Exception as e:
        return CheckResult(
            name="Network",
            passed=False,
            message=f"Network check failed: {str(e)}",
            fix="Check network connection and proxy settings",
        )


def check_samplesheet(path: str) -> CheckResult:
    """Validate an nf-core-style samplesheet exists and has required columns."""
    if not path:
        return CheckResult(
            name="Samplesheet",
            passed=False,
            message="No samplesheet provided",
            fix="Pass --samplesheet path/to/samplesheet.csv",
        )
    dest = Path(path)
    if not dest.is_file():
        return CheckResult(
            name="Samplesheet",
            passed=False,
            message=f"Samplesheet not found: {dest}",
            fix="Generate one with generate_samplesheet.py",
        )
    with dest.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = [f.strip() for f in (reader.fieldnames or [])]
        rows = list(reader)
    required_any = [{"sample", "fastq_1"}, {"sample", "bam"}]
    ok = any(req.issubset(set(fields)) for req in required_any)
    if not ok or not rows:
        return CheckResult(
            name="Samplesheet",
            passed=False,
            message="Samplesheet missing sample/fastq columns or has no rows",
            details=f"columns={fields} n_rows={len(rows)}",
            fix="Need at least 'sample' plus fastq_1 or bam",
        )
    return CheckResult(
        name="Samplesheet",
        passed=True,
        message=f"{len(rows)} rows, columns={fields}",
    )


def check_pipeline_config(path: str) -> CheckResult:
    dest = Path(path)
    if not dest.is_file():
        return CheckResult(
            name="Config",
            passed=False,
            message=f"nextflow.config not found: {dest}",
            fix="Generate one with cluster_profile_generator.py",
        )
    text = dest.read_text(encoding="utf-8", errors="replace")
    has_profile = "profiles" in text or "process." in text or "executor" in text
    return CheckResult(
        name="Config",
        passed=has_profile,
        message="nextflow.config present" + ("" if has_profile else " but no profiles/executor block"),
        details=str(dest),
    )


def run_all_checks(
    *,
    samplesheet: Optional[str] = None,
    config: Optional[str] = None,
    skip_network: bool = False,
) -> EnvironmentReport:
    checks = [
        check_docker(),
        check_nextflow(),
        check_java(),
        check_resources(),
    ]
    if not skip_network:
        checks.append(check_network())
    if samplesheet is not None:
        checks.append(check_samplesheet(samplesheet))
    if config is not None:
        checks.append(check_pipeline_config(config))

    critical_checks = ["Docker", "Nextflow", "Java"]
    if samplesheet is not None:
        critical_checks.append("Samplesheet")
    if config is not None:
        critical_checks.append("Config")
    ready = all(c.passed for c in checks if c.name in critical_checks)

    recommendations = []
    for check in checks:
        if not check.passed and check.fix:
            recommendations.append(f"{check.name}: {check.fix}")
        elif check.passed and check.fix:
            recommendations.append(f"{check.name} (warning): {check.fix}")

    return EnvironmentReport(ready=ready, checks=checks, recommendations=recommendations)


def print_report(report: EnvironmentReport):
    print("\n" + "=" * 50)
    print("  nf-core Environment Check")
    print("=" * 50 + "\n")

    for check in report.checks:
        status = "\033[92m[PASS]\033[0m" if check.passed else "\033[91m[FAIL]\033[0m"
        print(f"{status} {check.name}: {check.message}")

        if check.details:
            print(f"       {check.details}")

        if not check.passed and check.fix:
            print(f"       \033[93mFix:\033[0m {check.fix}")
        elif check.passed and check.fix:
            print(f"       \033[93mWarning:\033[0m {check.fix}")

    print()
    if report.ready:
        print("\033[92mEnvironment is READY for nf-core pipelines.\033[0m")
    else:
        print("\033[91mEnvironment is NOT READY. Please address the issues above.\033[0m")

    if report.recommendations:
        print("\n--- Recommendations ---")
        for i, rec in enumerate(report.recommendations, 1):
            print(f"  {i}. {rec}")

    print()


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Check environment for nf-core pipeline execution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
        "    python check_environment.py           # Human-readable output\n"
        "    python check_environment.py --json    # JSON output for parsing\n",
    )
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--samplesheet", default=None, help="Optional nf-core samplesheet to validate")
    parser.add_argument("--config", default=None, help="Optional nextflow.config to validate")
    parser.add_argument("--skip-network", action="store_true")

    args = parser.parse_args()

    report = run_all_checks(
        samplesheet=args.samplesheet,
        config=args.config,
        skip_network=args.skip_network,
    )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print_report(report)

    sys.exit(0 if report.ready else 1)


if __name__ == "__main__":
    main()
