#!/usr/bin/env python3
"""
실행 예시:
nohup python -u build_qcd_db.py \
    --fail-root /home/khshin/benchmark/fail/dataset \
    --bulk-json /home/khshin/benchmark/bulk/DFT/bulk.json \
    --bulk-poscar-root /home/khshin/benchmark/bulk/bulk \
    > build_qcd_db.log 2>&1 &
"""
import argparse
import json
import re
from pathlib import Path

import numpy as np
from ase import Atoms
from ase.calculators.singlepoint import SinglePointCalculator
from ase.data import atomic_numbers
from ase.db import connect
from ase.io import read as ase_read
from tqdm import tqdm

DB_PATH = Path(__file__).resolve().parent / "qcd_cluster.db"


_RE_SIGMA0 = re.compile(r"energy\(sigma->0\)\s*=\s*([+-]?\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?)")
_RE_TOTEN = re.compile(r"TOTEN\s*=\s*([+-]?\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?)\s*eV")


def _parse_float_triplet(line: str):
    parts = line.strip().split()
    if len(parts) < 3:
        return None
    try:
        return float(parts[0]), float(parts[1]), float(parts[2])
    except Exception:
        return None


def parse_outcar_steps(outcar_path: Path, natoms_expected: int):
    steps = []
    current_cell = None
    last_sigma0 = None
    last_toten = None

    in_pos_block = False
    pending_read_pos = 0
    pos_buf = []
    frc_buf = []

    last_step_idx = None

    def _finalize_step(step_idx, positions, forces, cell, energy):
        steps.append(
            dict(
                step=step_idx,
                positions=np.asarray(positions, dtype=float),
                forces=np.asarray(forces, dtype=float),
                cell=None if cell is None else np.asarray(cell, dtype=float),
                energy=energy,
            )
        )

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
                v1 = _parse_float_triplet(next(f, ""))
                v2 = _parse_float_triplet(next(f, ""))
                v3 = _parse_float_triplet(next(f, ""))
                if v1 and v2 and v3:
                    current_cell = np.array([v1, v2, v3], dtype=float)
                    if last_step_idx is not None and last_step_idx < len(steps):
                        steps[last_step_idx]["cell"] = current_cell.copy()
                continue

            if (not in_pos_block) and ("POSITION" in line and "TOTAL-FORCE" in line):
                in_pos_block = True
                pos_buf = []
                frc_buf = []
                pending_read_pos = natoms_expected

                next(f, "")

                step_idx = len(steps)
                last_step_idx = step_idx

                continue

            if in_pos_block:
                s = line.strip()
                if not s or s.startswith("-"):
                    continue

                parts = s.split()
                if len(parts) < 6:
                    continue

                try:
                    px, py, pz = float(parts[0]), float(parts[1]), float(parts[2])
                    fx, fy, fz = float(parts[3]), float(parts[4]), float(parts[5])
                except Exception:
                    continue

                pos_buf.append((px, py, pz))
                frc_buf.append((fx, fy, fz))
                pending_read_pos -= 1

                if pending_read_pos <= 0:
                    in_pos_block = False
                    energy = last_sigma0 if last_sigma0 is not None else last_toten
                    cell_for_step = None if current_cell is None else current_cell.copy()
                    _finalize_step(last_step_idx, pos_buf, frc_buf, cell_for_step, energy)
                continue

            if last_step_idx is not None and last_step_idx < len(steps):
                if last_sigma0 is not None:
                    steps[last_step_idx]["energy"] = last_sigma0
                elif last_toten is not None and steps[last_step_idx]["energy"] is None:
                    steps[last_step_idx]["energy"] = last_toten

    if not steps:
        return []

    last_cell = None
    for s in steps:
        if s["cell"] is not None:
            last_cell = s["cell"]
        else:
            s["cell"] = last_cell

    steps = [s for s in steps if s["cell"] is not None and s["energy"] is not None]
    return steps


def iter_bulk_entries(bulk_json: Path):
    data = json.loads(bulk_json.read_text())
    entries = data.get("best_entries", {})

    for elem, entry in entries.items():
        energy = entry["sigma0_eV"]
        natoms = entry["natoms"]
        poscar = BULK_POSCAR_ROOT / elem / "POSCAR"

        if poscar.exists():
            atoms = ase_read(str(poscar))
        else:
            Z = atomic_numbers[elem]
            atoms = Atoms(numbers=[Z] * natoms, pbc=False)

        calc = SinglePointCalculator(atoms, energy=float(energy))
        atoms.calc = calc

        kvp = dict(element=elem, n_atoms=int(natoms), type="bulk")
        yield atoms, kvp


def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = connect(str(DB_PATH))
    errors = []

    outcars = sorted(FAIL_ROOT.rglob("OUTCAR"))
    print(f"[cluster] OUTCAR 파일 수: {len(outcars)}")

    with db:
        done_cluster = set()
        for row in db.select(type="cluster"):
            done_cluster.add((str(row.calc_id), int(row.step)))

        cluster_new = 0
        cluster_skipped = 0

        for outcar in tqdm(outcars, desc="OUTCAR 변환 중"):
            try:
                parts = outcar.parts
                if len(parts) < 4:
                    continue
                calc_id = outcar.parent.name
                natoms = int(outcar.parent.parent.name)
                elem = outcar.parent.parent.parent.name

                Z = atomic_numbers.get(elem, None)
                if Z is None:
                    raise RuntimeError(f"unknown element: {elem}")

                steps = parse_outcar_steps(outcar, natoms_expected=natoms)
                if not steps:
                    continue

                for i, s in enumerate(steps):
                    step_idx = int(s["step"])
                    if (calc_id, step_idx) in done_cluster:
                        cluster_skipped += 1
                        continue

                    positions = s["positions"]
                    forces = s["forces"]
                    cell = s["cell"]
                    energy = float(s["energy"])

                    atoms = Atoms(numbers=[Z] * natoms, positions=positions, cell=cell, pbc=False)
                    calc = SinglePointCalculator(atoms, energy=energy, forces=forces)
                    atoms.calc = calc

                    is_last = 1 if i == (len(steps) - 1) else 0
                    kvp = dict(
                        element=elem,
                        n_atoms=natoms,
                        calc_id=calc_id,
                        step=step_idx,
                        is_last=is_last,
                        type="cluster",
                    )
                    db.write(atoms, **kvp)
                    cluster_new += 1

            except Exception as e:
                errors.append((str(outcar), str(e)))

        print(f"  cluster 신규: {cluster_new:,}개  /  스킵: {cluster_skipped:,}개")

        done_bulk = {row.element for row in db.select(type="bulk")}
        bulk_new = 0
        for atoms, kvp in iter_bulk_entries(BULK_JSON):
            if kvp["element"] in done_bulk:
                continue
            db.write(atoms, **kvp)
            bulk_new += 1
        print(f"[bulk] 신규: {bulk_new}개")

    print("\n완료!")
    print(f"  DB: {DB_PATH}")
    print(f"  cluster 신규: {cluster_new:,}")
    print(f"  bulk 신규: {bulk_new}")

    if errors:
        print(f"\n오류 {len(errors)}건 (상위 10개):")
        for p, m in errors[:10]:
            print(f"  {p}: {m}")
        err_log = DB_PATH.parent / "build_errors.log"
        err_log.write_text("\n".join(f"{p}\t{m}" for p, m in errors))
        print(f"  -> {err_log}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build QCD cluster ASE database from OUTCAR files.")
    parser.add_argument("--fail-root", required=True, type=Path,
                        help="Root directory containing OUTCAR files, organized as <elem>/<natoms>/<calc_id>/OUTCAR")
    parser.add_argument("--bulk-json", required=True, type=Path,
                        help="Path to bulk.json with best_entries")
    parser.add_argument("--bulk-poscar-root", required=True, type=Path,
                        help="Root directory containing bulk POSCAR files, organized as <elem>/POSCAR")
    args = parser.parse_args()

    FAIL_ROOT = args.fail_root
    BULK_JSON = args.bulk_json
    BULK_POSCAR_ROOT = args.bulk_poscar_root

    main()