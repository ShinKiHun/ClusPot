"""
ClusterBench Calculation Module

Reads all source DBs in data/ folder, performs MLIP single-point calculations,
and saves results to {work_dir}/data/{mlip_name}/{src_db_stem}.db.
(source DB = *.db directly under data/, results saved to data/{mlip_name}/ subfolder)

Usage:
    from cluspotlib import ClusterCalculation

    calc   = CHGNetCalculator(...)
    runner = ClusterCalculation(calc, mlip_name="CHGNet", work_dir=".")
    runner.run()                       # all source DBs × (bulk + cluster)
    runner.run(targets=["cluster"])    # cluster only
    runner.run(targets=["bulk"])       # bulk only
"""

import json
import logging
import sqlite3
import time
from pathlib import Path

import numpy as np
from ase import Atoms
from ase.calculators.singlepoint import SinglePointCalculator
from ase.db import connect


# ─────────────────────────────────────────────
# internal utilities
# ─────────────────────────────────────────────

def _setup_logger(mlip_name: str) -> logging.Logger:
    logger = logging.getLogger(f"clusterbench.{mlip_name}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    ch  = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    return logger


def _switch_log_file(logger: logging.Logger, log_dir: Path, db_stem: str, target: str):
    """Switch log file per DB + target (bulk/cluster)."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{db_stem}_{target}_{time.strftime('%Y%m%d_%H%M%S')}.log"

    # remove existing FileHandlers
    for h in logger.handlers[:]:
        if isinstance(h, logging.FileHandler):
            h.close()
            logger.removeHandler(h)

    fmt = logging.Formatter("%(asctime)s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    fh  = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    logger.info(f"Log file: {log_path}")


def _load_done_keys(dst_db_path: Path) -> set:
    """dst DB에서 (calc_id, step) 쌍만 raw SQL로 빠르게 읽기."""
    if not dst_db_path.exists():
        return set()
    conn = sqlite3.connect(str(dst_db_path))
    rows = conn.execute("SELECT key_value_pairs FROM systems").fetchall()
    conn.close()
    done = set()
    for (kvp_json,) in rows:
        kvp = json.loads(kvp_json) if kvp_json else {}
        if "calc_id" in kvp and "step" in kvp:
            done.add((kvp["calc_id"], int(kvp["step"])))
    return done


def _fmt_time(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02}:{(s % 3600) // 60:02}:{s % 60:02}"


def _single_point(calc, atoms):
    """
    Perform single-point calculation.

    Returns:
        energy    (float)  : total energy [eV]
        forces    (list)   : per-atom forces [eV/Å]
        calc_time (float)  : calculation elapsed time [s]
        converged (bool)   : True if no NaN/Inf in energy·forces
    """
    atoms = atoms.copy()
    atoms.calc = calc
    t0        = time.time()
    energy    = float(atoms.get_potential_energy())
    forces    = np.asarray(atoms.get_forces(), dtype=float).tolist()
    calc_time = time.time() - t0

    forces_arr = np.array(forces)
    converged  = (
        np.isfinite(energy)
        and bool(np.all(np.isfinite(forces_arr)))
    )
    return energy, forces, calc_time, converged


# ─────────────────────────────────────────────
# main class
# ─────────────────────────────────────────────

class ClusterCalculation:
    """
    Bulk / Cluster single-point calculation class.

    Args:
        calculator : ASE calculator object (CHGNet, MACE, SevenNet, etc.)
        mlip_name  : MLIP name (used as result DB subfolder name, e.g. "CHGNet")
        work_dir   : working directory. Defaults to current directory (CWD).
                     Must contain source DBs under data/ folder.
        overwrite  : if True, recalculate already-computed entries (default: False)
    """

    def __init__(
        self,
        calculator,
        mlip_name: str,
        work_dir=None,
        overwrite: bool = False,
    ):
        if calculator is None:
            raise ValueError("calculator is required.")
        if not mlip_name:
            raise ValueError("mlip_name is required. e.g. mlip_name='CHGNet'")

        self.calc      = calculator
        self.mlip_name = mlip_name
        self.overwrite = overwrite
        self.work_dir  = Path(work_dir).resolve() if work_dir else Path.cwd()
        self.data_dir  = self.work_dir / "data"

        self.log = _setup_logger(mlip_name)

        self.log.info(f"mlip_name : {self.mlip_name}")
        self.log.info(f"work_dir  : {self.work_dir}")
        self.log.info(f"data_dir  : {self.data_dir}")

    def _find_src_dbs(self) -> list:
        """Return *.db files directly under data/ as source DBs (excluding result subfolders)."""
        if not self.data_dir.exists():
            raise FileNotFoundError(f"data folder not found: {self.data_dir}")
        src_dbs = sorted(self.data_dir.glob("*.db"))
        if not src_dbs:
            raise FileNotFoundError(f"no source DB found: {self.data_dir}/*.db")
        return src_dbs

    # ── public methods ──────────────────────────────

    def run(self, targets: list = None):
        """
        Run calculations for all source DBs under data/ folder.

        Args:
            targets: ["bulk"], ["cluster"], or None (run both)
        """
        all_targets = ["bulk", "cluster"]
        targets = targets or all_targets

        invalid = [t for t in targets if t not in all_targets]
        if invalid:
            raise ValueError(f"unknown target(s): {invalid}. valid values: {all_targets}")

        src_dbs = self._find_src_dbs()

        self.log.info("=" * 60)
        self.log.info(f"ClusterCalculation  |  model: {self.mlip_name}")
        self.log.info(f"targets   : {targets}")
        self.log.info(f"Source DBs: {[p.name for p in src_dbs]}")
        self.log.info("=" * 60)

        for src_db_path in src_dbs:
            dst_db_path = self.data_dir / self.mlip_name / f"{src_db_path.stem}.db"
            dst_db_path.parent.mkdir(parents=True, exist_ok=True)

            self.log.info(f"\n[DB] {src_db_path.name}  →  {dst_db_path.relative_to(self.work_dir)}")

            src = connect(str(src_db_path))
            dst = connect(str(dst_db_path))

            # persistent connection으로 write 배치 처리 (5000건마다 commit)
            con = dst._connect()
            dst._initialize(con)
            dst.connection = con
            dst.change_count = 0
            try:
                if "bulk"    in targets:
                    _switch_log_file(self.log, self.work_dir / "log" / self.mlip_name, src_db_path.stem, "bulk")
                    self._run_bulk(src, dst)
                if "cluster" in targets:
                    _switch_log_file(self.log, self.work_dir / "log" / self.mlip_name, src_db_path.stem, "cluster")
                    self._run_cluster(src, dst, dst_db_path)
            finally:
                con.commit()
                con.close()
                dst.connection = None

        self.log.info(f"[ALL DONE] {self.mlip_name}")

    # ── Bulk ─────────────────────────────────────

    def _run_bulk(self, src, dst):
        self.log.info("[BULK] start")
        rows = list(src.select(type="bulk"))
        self.log.info(f"[BULK] total rows: {len(rows)}")

        done = set() if self.overwrite else {
            row.element for row in dst.select(type="bulk")
        }

        t0 = time.time()
        done_count = skipped = failed = 0

        n = len(rows)
        for i, row in enumerate(rows, 1):
            elem = row.element
            if elem in done:
                skipped += 1
                continue

            try:
                atoms                     = row.toatoms()
                energy, forces, ct, conv  = _single_point(self.calc, atoms)
                epa                       = energy / len(atoms)

                dummy      = Atoms()
                dummy.calc = SinglePointCalculator(dummy, energy=energy)
                src_path = getattr(row, "src_path", None)
                dst.write(
                    dummy,
                    element=elem,
                    n_atoms=len(atoms),
                    energy_per_atom=epa,
                    calc_time=ct,
                    type="bulk",
                    **({} if src_path is None else {"src_path": src_path}),
                )

                self.log.info(
                    f"  [{i:>{len(str(n))}}/{n}]  {elem:<3}  "
                    f"n={len(atoms):>4}  "
                    f"E/atom={epa:>10.6f} eV  "
                    f"t={ct:>7.3f}s  "
                    f"converged={conv}"
                )
                done_count += 1

            except Exception as e:
                self.log.error(
                    f"  [{i:>{len(str(n))}}/{n}]  {elem:<3}  ERROR: {e}"
                )
                failed += 1

        self.log.info(
            f"[BULK] done ({_fmt_time(time.time() - t0)})  "
            f"done={done_count}  skipped={skipped}  failed={failed}"
        )

    # ── Cluster ──────────────────────────────────

    def _run_cluster(self, src, dst, dst_db_path: Path):
        self.log.info("[CLUSTER] start")
        rows  = list(src.select(type="cluster"))
        total = len(rows)
        self.log.info(f"[CLUSTER] total rows: {total}")

        done = set() if self.overwrite else _load_done_keys(dst_db_path)
        self.log.info(f"[CLUSTER] already done: {len(done)}")

        t0 = time.time()
        done_count = skipped = failed = 0

        w = len(str(total))
        SUMMARY_INTERVAL = 100

        for i, row in enumerate(rows, 1):
            key = (row.calc_id, row.step)
            if key in done:
                skipped += 1
                continue

            try:
                atoms                     = row.toatoms()
                energy, forces, ct, conv  = _single_point(self.calc, atoms)

                result      = row.toatoms()
                result.calc = SinglePointCalculator(
                    result, energy=energy, forces=np.array(forces)
                )
                src_path = getattr(row, "src_path", None)
                dst.write(
                    result,
                    element=row.element,
                    n_atoms=row.n_atoms,
                    calc_id=row.calc_id,
                    step=row.step,
                    is_last=row.is_last,
                    calc_time=ct,
                    type="cluster",
                    **({} if src_path is None else {"src_path": src_path}),
                )

                self.log.info(
                    f"  [{i:>{w}}/{total}]  {row.element:<3}  "
                    f"id={row.calc_id[:8]}  step={row.step:>4}  "
                    f"n={row.n_atoms:>4}  "
                    f"E={energy:>12.6f} eV  "
                    f"t={ct:>7.3f}s  "
                    f"converged={conv}"
                )
                done_count += 1

            except Exception as e:
                self.log.error(
                    f"  [{i:>{w}}/{total}]  {row.element:<3}  "
                    f"id={row.calc_id[:8]}  step={row.step:>4}  ERROR: {e}"
                )
                failed += 1

            if i % SUMMARY_INTERVAL == 0 or i == total:
                dt   = time.time() - t0
                rate = i / dt if dt > 0 else 0
                eta  = (total - i) / rate if rate > 0 else 0
                self.log.info(
                    f"  ── [SUMMARY {i:>{w}}/{total}]  {i / total * 100:5.1f}%  "
                    f"rate={rate:5.2f} str/s  ETA={_fmt_time(eta)}  "
                    f"done={done_count}  skipped={skipped}  failed={failed}"
                )

        self.log.info(
            f"[CLUSTER] done ({_fmt_time(time.time() - t0)})  "
            f"done={done_count}  skipped={skipped}  failed={failed}"
        )
