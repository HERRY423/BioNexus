# Bio Research Plugin — Short-Term Fixes

> 基于深度审阅报告 (2026-07-23) 中的 5 个短期改进任务。
> 原始插件路径: `~/.claude/plugins/marketplaces/obsidian-local/plugins/bio-research`
> 改动版路径: `C:\Plugin\bio-research`

---

## Fix #1: remove `filter_cells()` fake `inplace` parameter

**File:** `skills/single-cell-rna-qc/scripts/qc_core.py`

**Problem:** `filter_cells(adata, mask, inplace=False)` always returns `.copy()` regardless of the `inplace` flag. The parameter name misleads callers into thinking in-place filtering is possible.

**Change:**
- Removed the `inplace` parameter entirely
- Updated docstring to explicitly state "always returns a new AnnData object — assign the result"
- Updated the call site in `qc_analysis.py`

---

## Fix #2: deduplicate `train_model.py` and `model_utils.py`

**File:** `skills/scvi-tools/scripts/train_model.py`

**Problem:** `train_model.py` and `model_utils.py` independently implemented the same functions (train_scvi, train_scanvi), creating dual maintenance burden and potential divergence.

**Change:**
- Rewrote `train_model.py` as a thin CLI wrapper
- `train_scvi`/`train_scanvi` now imported from `model_utils` (single source of truth)
- Only CLI dispatch logic and model-specific functions (totalvi/peakvi/velovi/multivi) remain
- File reduced from ~370 to ~210 lines

---

## Fix #3: add Windows support to `check_environment.py`

**File:** `skills/nextflow-development/scripts/check_environment.py`

**Problem:** Resource detection only worked on Linux (`/proc/meminfo`) and macOS (`sysctl`). On Windows, `mem_gb` and `disk_gb` both returned 0, producing false "Low memory" and "Low disk space" warnings.

**Change:**
- Added `import platform` and `_IS_WINDOWS` / `_IS_MACOS` / `_IS_LINUX` platform detection
- New `_get_memory_gb()` — Windows queries TotalPhysicalMemory via PowerShell/CIM with wmic fallback
- New `_get_disk_gb()` — Windows uses `kernel32.GetDiskFreeSpaceExW`
- `check_resources()` now includes OS info in its details output
- `check_docker()` and `check_java()` provide Windows-specific fix suggestions

---

## Fix #4: expand instrument detection coverage in `convert_to_asm.py`

**File:** `skills/instrument-data-to-allotrope/scripts/convert_to_asm.py`

**Problem:** `supported_instruments.md` listed 40+ instruments but `DETECTION_PATTERNS` only covered 8, forcing most instruments through the low-quality fallback parser.

**Change:**
- `DETECTION_PATTERNS` expanded from 8 to 27 entries, organized by category:
  - Cell Counting: +2 (NucleoView, Revvity Matrix)
  - Spectrophotometry: +2 (NanoDrop 8000, Lunatic)
  - Plate Readers: +3 (EnVision, SkanIt, Magellan)
  - qPCR: +3 (Design & Analysis, CFX Maestro, LightCycler)
  - ELISA: +1 (MSD Workbench)
  - Electrophoresis: +2 (TapeStation, LabChip)
  - Chromatography: +3 (Empower, Chromeleon, ChemStation)
  - Flow Cytometry: +1 (FACSDiva)
- Each entry includes column header fingerprints, keywords, and file extension patterns

---

## Fix #5: replace `--break-system-packages` with virtual environment guidance

**Files:**
- `skills/instrument-data-to-allotrope/SKILL.md`
- `skills/instrument-data-to-allotrope/requirements.txt`
- `skills/instrument-data-to-allotrope/scripts/convert_to_asm.py`

**Problem:** `--break-system-packages` is a Debian/Ubuntu PEP 668 workaround. It does not apply on conda environments or Windows. Recommending it encourages poor Python packaging practices.

**Change:**
- All `pip install ... --break-system-packages` replaced with:
  1. Virtual environment creation instructions (venv, with Linux/macOS/Windows commands)
  2. Standard `pip install` commands
- `requirements.txt` comment and `convert_to_asm.py` error message updated accordingly

---

## Unchanged

- Original plugin files (`~/.claude/plugins/...`) are completely untouched
- All non-target files in `C:\Plugin\bio-research\` are identical copies of the originals
- `.mcp.json`, `plugin.json`, `CONNECTORS.md`, `README.md` were not modified

---

*Date: 2026-07-23*
