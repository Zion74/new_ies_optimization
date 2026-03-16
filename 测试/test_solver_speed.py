# -*- coding: utf-8 -*-
"""
测试 Gurobi vs GLPK 在子进程中的可用性和速度对比
"""
import os, sys, io, time, multiprocessing as mp

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

os.environ["GRB_LICENSE_FILE"] = r"C:\Users\ikun\gurobi.lic"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _solve_once(solver_name):
    """在当前进程中用指定求解器跑一次 OperationModel，返回耗时"""
    os.environ.setdefault("GRB_LICENSE_FILE", r"C:\Users\ikun\gurobi.lic")
    from operation import OperationModel
    import oemof.solph as solph

    T = 24
    m = OperationModel(
        "01/01/2019", T,
        [0.0025]*T, [0.0286]*T,
        [100.]*T, [80.]*T, [50.]*T,
        [30.]*T, [20.]*T,
        500, 200, 100, 100, 500, 200, 100,
    )
    # 强制指定求解器，绕过自动回退逻辑
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        t0 = time.time()
        results = m.model.solve(solver=solver_name, solve_kwargs={"tee": False})
        elapsed = time.time() - t0
    return elapsed


def _worker(args):
    solver, idx = args
    os.environ.setdefault("GRB_LICENSE_FILE", r"C:\Users\ikun\gurobi.lic")
    try:
        t = _solve_once(solver)
        return (solver, idx, t, None)
    except Exception as e:
        return (solver, idx, None, str(e))


def main():
    REPEATS = 3  # 每个求解器重复次数

    print("=" * 55)
    print("  求解器速度对比测试（单进程 + 多进程子进程）")
    print("=" * 55)

    # ── 1. 主进程测试 ────────────────────────────────────
    print("\n[主进程]")
    for solver in ("gurobi", "glpk"):
        times = []
        for _ in range(REPEATS):
            try:
                t = _solve_once(solver)
                times.append(t)
            except Exception as e:
                print(f"  {solver}: 失败 → {e}")
                break
        if times:
            avg = sum(times) / len(times)
            print(f"  {solver:8s}: 平均 {avg:.3f}s  (×{REPEATS})")

    # ── 2. 子进程测试 ────────────────────────────────────
    print("\n[子进程 — multiprocessing.Pool]")
    tasks = [(s, i) for s in ("gurobi", "glpk") for i in range(REPEATS)]
    with mp.Pool(processes=2) as pool:
        results = pool.map(_worker, tasks)

    for solver in ("gurobi", "glpk"):
        rows = [(s, i, t, e) for s, i, t, e in results if s == solver]
        ok = [t for _, _, t, e in rows if t is not None]
        errs = [e for _, _, t, e in rows if e is not None]
        if ok:
            avg = sum(ok) / len(ok)
            print(f"  {solver:8s}: 平均 {avg:.3f}s  (×{len(ok)})")
        if errs:
            print(f"  {solver:8s}: {len(errs)} 次失败 → {errs[0][:80]}")

    print("\n" + "=" * 55)
    print("结论：")
    print("  - 若 Gurobi 子进程可用且比 GLPK 快，说明修复生效")
    print("  - 若 Gurobi 子进程仍失败，检查 GRB_LICENSE_FILE 路径")
    print("=" * 55)


if __name__ == "__main__":
    main()
