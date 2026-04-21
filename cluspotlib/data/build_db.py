#!/usr/bin/env python3
"""
build_db.py — Generalized DFT OUTCAR → ASE DB builder

Supports monoelement, bimetallic, and HEA clusters.
Species information is read directly from OUTCAR (VRHFIN + ions per type).
calc_id is derived from the relative path (reproducible, 28-char URL-safe base64).

Directory structure:
  data/
    user_cluster/
      <anything>/.../<calc_folder>/OUTCAR   (any structure, searched recursively)
    user_bulk/
      <anything>/.../<elem_folder>/OUTCAR   (any structure, searched recursively; one OUTCAR per element)

cluster_dir and bulk_dir must not overlap: rglob under cluster_dir will treat
every OUTCAR it finds as a cluster entry, including any nested bulk folders.

Usage:
    python build_db.py --cluster-dir /path/to/user_cluster \\
                       --bulk-dir    /path/to/user_bulk \\
                       --out         data/cluster.db
    python build_db.py --cluster-dir ... --bulk-dir ... --out ... --overwrite
"""

import argparse
import base64
import hashlib
import re
from pathlib import Path

import numpy as np
from ase import Atoms
from ase.calculators.singlepoint import SinglePointCalculator
from ase.data import atomic_numbers
from ase.db import connect
from tqdm import tqdm


_RE_SIGMA0   = re.compile(r"energy\(sigma->0\)\s*=\s*([-\d.E+]+)", re.IGNORECASE)
_RE_TOTEN    = re.compile(r"free\s+energy\s+TOTEN\s*=\s*([-\d.E+]+)", re.IGNORECASE)
_RE_VRHFIN   = re.compile(r"VRHFIN\s*=\s*([A-Za-z]+)\s*:")
_RE_IONS     = re.compile(r"ions per type\s*=\s*([\d\s]+)")
_RE_ITER     = re.compile(r"^\s*-+\s*Iteration\s+\d+", re.IGNORECASE)
_RE_ABORT    = re.compile(r"aborting\s+loop", re.IGNORECASE)
_RE_ADDDIP   = re.compile(r"adding\s+dipol\s+energy\s+to\s+TOTEN\s+NOW", re.IGNORECASE)
_RE_REACHED  = re.compile(r"reached\s+required\s+accuracy", re.IGNORECASE)


# ── Utilities ────────────────────────────────────────────────────────────────

def _make_calc_id(rel_path: str) -> str:
    """Reproducible 28-char URL-safe base64 ID derived from relative path."""
    h = hashlib.sha256(rel_path.encode()).digest()[:21]
    return base64.urlsafe_b64encode(h).decode()


# ── OUTCAR parsing ────────────────────────────────────────────────────────────

def parse_bulk_energy(outcar_path: Path) -> float:
    """
    Read the last converged energy(sigma->0) from OUTCAR ionic loop.

    - Only reads sigma->0 paired with 'free energy TOTEN' inside the ionic loop.
    - Stops at 'aborting loop' or 'adding dipol energy to TOTEN NOW'.
    - Raises RuntimeError if SCF not converged or energy not found.
    """
    try:
        lines = outcar_path.read_text(errors="ignore").splitlines()
    except OSError as e:
        raise RuntimeError(f"cannot read OUTCAR: {e}")

    # check SCF convergence
    converged = any(_RE_REACHED.search(l) for l in lines)
    if not converged:
        raise RuntimeError("SCF not converged (reached required accuracy not found)")

    last_sigma0 = None
    in_ionic    = False

    for i, line in enumerate(lines):
        if _RE_ITER.search(line):
            in_ionic = True

        if in_ionic and (_RE_ABORT.search(line) or _RE_ADDDIP.search(line)):
            break

        if not in_ionic:
            continue

        if _RE_TOTEN.search(line):
            for j in (i + 1, i + 2, i + 3):
                if j >= len(lines):
                    break
                m = _RE_SIGMA0.search(lines[j])
                if m:
                    try:
                        last_sigma0 = float(m.group(1))
                    except ValueError:
                        pass
                    break

    if last_sigma0 is None:
        raise RuntimeError("energy(sigma->0) not found in ionic loop")
    return last_sigma0


def parse_outcar_species(outcar_path: Path):
    """
    Parse species and per-type atom counts from OUTCAR header.

    Returns:
        species (list[str]) : e.g. ['Ag', 'Au']
        counts  (list[int]) : e.g. [35, 20]
    """
    species = []
    counts  = []

    with outcar_path.open("r", errors="ignore") as f:
        for line in f:
            m = _RE_VRHFIN.search(line)
            if m:
                species.append(m.group(1))

            m2 = _RE_IONS.search(line)
            if m2:
                counts = [int(x) for x in m2.group(1).split()]
                break  # ions per type always appears after all VRHFIN lines

    return species, counts


def parse_outcar_steps(outcar_path: Path, natoms_expected: int):
    """
    Parse all ionic steps (positions, forces, energy, cell) from OUTCAR.

    Returns:
        list of dicts with keys: step, positions, forces, cell, energy
    """
    steps         = []
    current_cell  = None
    last_sigma0   = None
    last_toten    = None
    in_pos_block  = False
    pending       = 0
    pos_buf       = []
    frc_buf       = []
    last_step_idx = None

    def _triplet(line):
        # handle concatenated signed numbers, e.g. "1.234-5.678" → "1.234 -5.678"
        # (digit immediately followed by + or -, but not in scientific notation like 1E-4)
        line = re.sub(r'(\d)([+-])(?![Ee])', r'\1 \2', line)
        parts = line.strip().split()
        if len(parts) < 3:
            return None
        try:
            return float(parts[0]), float(parts[1]), float(parts[2])
        except Exception:
            return None

    def _finalize(step_idx, positions, forces, cell, energy):
        steps.append(dict(
            step=step_idx,
            positions=np.asarray(positions, dtype=float),
            forces=np.asarray(forces, dtype=float),
            cell=None if cell is None else np.asarray(cell, dtype=float),
            energy=energy,
        ))

    with outcar_path.open("r", errors="ignore") as f:
        for line in f:
            m = _RE_SIGMA0.search(line)
            if m:
                try:
                    last_sigma0 = float(m.group(1))
                except Exception:
                    pass

            m2 = _RE_TOTEN.search(line)
            if m2:
                try:
                    last_toten = float(m2.group(1))
                except Exception:
                    pass

            if "direct lattice vectors" in line:
                v1, v2, v3 = _triplet(next(f, "")), _triplet(next(f, "")), _triplet(next(f, ""))
                if v1 and v2 and v3:
                    current_cell = np.array([v1, v2, v3], dtype=float)
                continue

            if (not in_pos_block) and ("POSITION" in line and "TOTAL-FORCE" in line):
                in_pos_block  = True
                pos_buf       = []
                frc_buf       = []
                pending       = natoms_expected
                last_step_idx = len(steps)
                next(f, "")  # skip dashed separator
                continue

            if in_pos_block:
                s = line.strip()
                if not s or s.startswith("-"):
                    continue
                parts = s.split()
                if len(parts) < 6:
                    continue
                try:
                    pos_buf.append((float(parts[0]), float(parts[1]), float(parts[2])))
                    frc_buf.append((float(parts[3]), float(parts[4]), float(parts[5])))
                except Exception:
                    continue
                pending -= 1
                if pending <= 0:
                    in_pos_block = False
                    energy = last_sigma0 if last_sigma0 is not None else last_toten
                    cell   = None if current_cell is None else current_cell.copy()
                    _finalize(last_step_idx, pos_buf, frc_buf, cell, energy)

    if not steps:
        return []

    # forward-fill missing cells
    last_cell = None
    for s in steps:
        if s["cell"] is not None:
            last_cell = s["cell"]
        else:
            s["cell"] = last_cell

    return [s for s in steps if s["cell"] is not None and s["energy"] is not None]


# ── DB builders ───────────────────────────────────────────────────────────────

def _build_cluster(db, cluster_root: Path, data_dir: Path, overwrite: bool):
    outcars = sorted(cluster_root.rglob("OUTCAR"))
    print(f"[cluster] OUTCARs found: {len(outcars)}")

    done = set() if overwrite else {
        (row.calc_id, int(row.step)) for row in db.select(type="cluster")
    }

    new = skipped = failed = 0

    for outcar in tqdm(outcars, desc="cluster"):
        try:
            rel_path = str(outcar.parent.relative_to(data_dir))
            calc_id  = _make_calc_id(rel_path)

            species, counts = parse_outcar_species(outcar)
            if not species or not counts or len(species) != len(counts):
                raise RuntimeError(f"species parse failed: species={species}, counts={counts}")

            natoms  = sum(counts)
            numbers = []
            for elem, cnt in zip(species, counts):
                numbers.extend([atomic_numbers[elem]] * cnt)
            element = "-".join(sorted(species))

            steps = parse_outcar_steps(outcar, natoms)
            if not steps:
                raise RuntimeError("no ionic steps parsed")

            for i, s in enumerate(steps):
                step_idx = int(s["step"])
                if (calc_id, step_idx) in done:
                    skipped += 1
                    continue

                atoms = Atoms(numbers=numbers, positions=s["positions"],
                              cell=s["cell"], pbc=False)
                atoms.calc = SinglePointCalculator(
                    atoms, energy=s["energy"], forces=s["forces"]
                )

                db.write(
                    atoms,
                    type="cluster",
                    element=element,
                    n_atoms=natoms,
                    calc_id=calc_id,
                    src_path=rel_path,
                    step=step_idx,
                    is_last=1 if i == len(steps) - 1 else 0,
                )
                new += 1

        except Exception as e:
            failed += 1
            print(f"  [ERROR] {outcar}: {e}")

    print(f"[cluster] new={new}  skipped={skipped}  failed={failed}")


def _build_bulk(db, bulk_root: Path, data_dir: Path, overwrite: bool):
    outcars = sorted(bulk_root.rglob("OUTCAR"))
    print(f"[bulk] OUTCARs found: {len(outcars)}")

    done = set() if overwrite else {
        row.element for row in db.select(type="bulk")
    }

    new = skipped = failed = 0

    for outcar in tqdm(outcars, desc="bulk"):
        try:
            rel_path = str(outcar.parent.relative_to(data_dir))

            species, counts = parse_outcar_species(outcar)
            if not species or not counts:
                raise RuntimeError("species parse failed")
            if len(species) != 1:
                raise RuntimeError(f"bulk OUTCAR has multiple species: {species}")

            element = species[0]
            if element in done:
                skipped += 1
                continue

            natoms  = sum(counts)
            numbers = [atomic_numbers[element]] * natoms

            energy = parse_bulk_energy(outcar)
            steps  = parse_outcar_steps(outcar, natoms)
            if not steps:
                raise RuntimeError("no ionic steps parsed (cannot get cell/positions)")
            last   = steps[-1]
            atoms  = Atoms(numbers=numbers, positions=last["positions"],
                           cell=last["cell"], pbc=True)
            atoms.calc = SinglePointCalculator(atoms, energy=energy)

            db.write(
                atoms,
                type="bulk",
                element=element,
                n_atoms=natoms,
                src_path=rel_path,
            )
            done.add(element)
            new += 1

        except Exception as e:
            failed += 1
            print(f"  [ERROR] {outcar}: {e}")

    print(f"[bulk] new={new}  skipped={skipped}  failed={failed}")


# ── Main ──────────────────────────────────────────────────────────────────────

def build_db(
    out_db: Path,
    cluster_dir: Path = None,
    bulk_dir: Path    = None,
    overwrite: bool   = False,
):
    """
    Build ASE DB from DFT OUTCARs.

    Args:
        out_db      : Output DB path.
        cluster_dir : Directory containing cluster OUTCARs (searched recursively).
        bulk_dir    : Directory containing bulk OUTCARs (searched recursively).
        overwrite   : If True, recalculate already-stored entries.
    """
    if cluster_dir is None and bulk_dir is None:
        raise ValueError("At least one of cluster_dir or bulk_dir must be provided.")

    out_db.parent.mkdir(parents=True, exist_ok=True)
    db = connect(str(out_db))

    if cluster_dir is not None:
        cluster_dir = cluster_dir.resolve()
        if not cluster_dir.exists():
            raise FileNotFoundError(f"cluster_dir not found: {cluster_dir}")
        _build_cluster(db, cluster_dir, cluster_dir.parent, overwrite)

    if bulk_dir is not None:
        bulk_dir = bulk_dir.resolve()
        if not bulk_dir.exists():
            raise FileNotFoundError(f"bulk_dir not found: {bulk_dir}")
        _build_bulk(db, bulk_dir, bulk_dir.parent, overwrite)

    print(f"\n[DONE] {out_db}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build ASE DB from DFT OUTCARs (mono / bimetallic / HEA)"
    )
    parser.add_argument("--cluster-dir", type=Path, default=None,
                        help="Directory containing cluster OUTCARs (searched recursively)")
    parser.add_argument("--bulk-dir",    type=Path, default=None,
                        help="Directory containing bulk OUTCARs (searched recursively)")
    parser.add_argument("--out",         required=True, type=Path,
                        help="Output DB path (e.g. data/bimetallic.db)")
    parser.add_argument("--overwrite",   action="store_true",
                        help="Recalculate already-stored entries")
    args = parser.parse_args()

    build_db(
        out_db=args.out,
        cluster_dir=args.cluster_dir,
        bulk_dir=args.bulk_dir,
        overwrite=args.overwrite,
    )
