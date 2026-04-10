# -*- coding: utf-8 -*-
"""
run.py — CCHP 优化实验启动器
==============================
用法：
  uv run python run.py              # 交互式选择模式
  uv run python run.py --mode test  # 测试模式（nind=10, maxgen=5）
  uv run python run.py --mode quick # 快速模式（nind=20, maxgen=20）
  uv run python run.py --mode full  # 正式模式（nind=50, maxgen=100，全部5种方法）
  uv run python run.py --mode custom --nind 40 --maxgen 80 --methods std euclidean
  uv run python run.py --check      # 仅做环境检查，不运行优化

论文四组实验（正式模式）：
  uv run python run.py --exp 1      # 实验1: 德国×5种方法（创新点1主实验）
  uv run python run.py --exp 2      # 实验2: 松山湖×方案B+C（普适性验证）
  uv run python run.py --exp 3      # 实验3: 松山湖×方案C 有/无卡诺电池（创新点2）
  uv run python run.py --exp 4      # 实验4: 松山湖+卡诺×方案B vs C（串联两个创新点）
  uv run python run.py --exp all    # 依次运行全部4组实验

  加 --test-run 可用测试参数快速验证流程：
  uv run python run.py --exp 1 --test-run

模式说明：
  test   快速验证流程是否正常（约 5-10 分钟）
  quick  初步结果，3种方法（约 20-40 分钟）
  full   完整对比实验，5种方法（约 1-3 小时）
  custom 自定义所有参数
"""

import sys
import io
import os
import argparse
import time
import datetime
import traceback

# Gurobi 许可证路径（主进程和子进程均需要）
os.environ.setdefault("GRB_LICENSE_FILE", r"C:\Users\ikun\gurobi.lic")

# ── 编码修复（Windows GBK 终端）──────────────────────────────────────────
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

os.environ["GRB_LICENSE_FILE"] = r"C:\Users\ikun\gurobi.lic"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# ── 预设配置 ─────────────────────────────────────────────────────────────
PRESETS = {
    "test": {
        "desc": "测试模式 — 快速验证流程（约 5-10 分钟）",
        "nind": 10,
        "maxgen": 5,
        "pool_type": "Process",
        "inherit_population": False,
        "methods": ["std", "euclidean"],
    },
    "quick": {
        "desc": "快速模式 — 初步结果（约 20-40 分钟）",
        "nind": 20,
        "maxgen": 20,
        "pool_type": "Process",
        "inherit_population": True,
        "methods": ["std", "euclidean", "economic_only"],
    },
    "full": {
        "desc": "正式模式 — 完整对比实验（约 1-3 小时）",
        "nind": 50,
        "maxgen": 100,
        "pool_type": "Process",
        "inherit_population": True,
        "methods": ["std", "euclidean", "pearson", "ssr", "economic_only"],
    },
}

ALL_METHODS = ["std", "euclidean", "pearson", "ssr", "economic_only"]

METHOD_DESC = {
    "std":           "方案B — 波动率匹配度（师兄方法）",
    "euclidean":     "方案C — 能质耦合欧氏距离（本文核心创新）",
    "pearson":       "方案D — 皮尔逊相关系数",
    "ssr":           "方案E — 供需重叠度SSR",
    "economic_only": "方案A — 单目标经济最优（基准）",
}

# ── 论文四组实验定义 ──────────────────────────────────────────────────────
EXPERIMENTS = {
    "1": {
        "name": "实验1: 德国案例×5种方法（创新点1-方法对比）",
        "case": "german",
        "carnot": False,
        "methods": ["economic_only", "std", "euclidean", "pearson", "ssr"],
        "inherit_population": True,
    },
    "2": {
        "name": "实验2: 松山湖案例×方案B+C（普适性验证）",
        "case": "songshan_lake",
        "carnot": False,
        "methods": ["std", "euclidean"],
        "inherit_population": True,
    },
    "3": {
        "name": "实验3: 松山湖×方案C 有/无卡诺电池（创新点2）",
        "case": "songshan_lake",
        "carnot": "both",  # 特殊标记：先跑无卡诺，再跑有卡诺
        "methods": ["euclidean"],
        "inherit_population": False,
    },
    "4": {
        "name": "实验4: 松山湖+卡诺×方案B vs C（串联创新点）",
        "case": "songshan_lake",
        "carnot": True,
        "methods": ["std", "euclidean"],
        "inherit_population": True,
    },
}


# ── 环境检查 ──────────────────────────────────────────────────────────────
def run_checks(verbose=True) -> bool:
    """运行前置环境检查，返回 True 表示全部通过"""
    checks = []

    def chk(name, fn):
        try:
            msg = fn()
            checks.append((True, name, msg or ""))
            if verbose:
                print(f"  [OK] {name}" + (f"  →  {msg}" if msg else ""))
        except Exception as e:
            checks.append((False, name, str(e)))
            if verbose:
                print(f"  [!!] {name}  →  {e}")

    if verbose:
        print("\n── 环境检查 ─────────────────────────────────────")

    chk("Python 依赖", lambda: (
        __import__("geatpy"),
        __import__("oemof.solph"),
        __import__("pyomo.environ"),
        "geatpy / oemof.solph / pyomo OK"
    )[-1])

    def _check_solvers():
        import pyomo.environ as pyo
        from pyomo.opt import SolverFactory
        ok = []
        for s in ["gurobi", "glpk"]:
            if SolverFactory(s).available():
                ok.append(s)
        assert ok, "没有可用求解器（gurobi / glpk）"
        return " + ".join(ok) + " 可用"
    chk("求解器", _check_solvers)

    def _check_data():
        import pandas as pd
        df = pd.read_csv(os.path.join(BASE_DIR, "data", "mergedData.csv"))
        assert df.shape == (8760, 6), f"mergedData.csv 行列数异常: {df.shape}"
        df2 = pd.read_excel(os.path.join(BASE_DIR, "data", "typicalDayData.xlsx"), engine="openpyxl")
        assert len(df2) == 14, f"typicalDayData.xlsx 典型日数量异常: {len(df2)}"
        return f"mergedData {df.shape}  typicalDayData {len(df2)} 典型日"
    chk("数据文件", _check_data)

    def _check_operation():
        from operation import OperationModel
        T = 24
        m = OperationModel(
            "01/01/2019", T,
            [0.0025]*T, [0.0286]*T,
            [100.]*T, [80.]*T, [50.]*T,
            [30.]*T, [20.]*T,
            500, 200, 100, 100, 500, 200, 100,
        )
        m.optimise()
        obj = m.get_objective_value()
        assert obj and obj > 0
        return f"目标值={obj:.2f}"
    chk("OperationModel 单次求解", _check_operation)

    passed = sum(1 for ok, _, _ in checks if ok)
    failed = len(checks) - passed
    if verbose:
        print(f"\n  检查结果：{passed} 通过，{failed} 失败")
        if failed:
            print("  存在失败项，建议先修复再运行优化。")
        print("─" * 50)
    return failed == 0


# ── 结果摘要打印 ──────────────────────────────────────────────────────────
def print_result_summary(results: dict, elapsed: float, result_dir: str):
    """优化完成后打印简洁的结果摘要"""
    print("\n" + "=" * 60)
    print("  实验结果摘要")
    print("=" * 60)

    rows = []
    for method, res in results.items():
        bi = res.get("best_indi")
        if bi is None or bi.sizes == 0:
            rows.append((METHOD_DESC.get(method, method), "—", "—", "—", 0))
            continue
        import numpy as np
        min_cost = np.min(bi.ObjV[:, 0])
        best_match = np.min(bi.ObjV[:, 1]) if bi.ObjV.shape[1] > 1 else None
        t = res.get("time", 0)
        rows.append((
            METHOD_DESC.get(method, method),
            f"{min_cost:,.0f} €",
            f"{best_match:.2f}" if best_match is not None else "—",
            f"{t:.0f}s",
            bi.sizes,
        ))

    col_w = [max(len(str(r[i])) for r in rows) for i in range(5)]
    col_w = [max(w, len(h)) for w, h in zip(col_w, ["方法", "最低成本", "最佳匹配度", "耗时", "Pareto解数"])]
    header = "  ".join(h.ljust(col_w[i]) for i, h in enumerate(["方法", "最低成本", "最佳匹配度", "耗时", "Pareto解数"]))
    print(f"\n  {header}")
    print("  " + "-" * len(header))
    for row in rows:
        print("  " + "  ".join(str(v).ljust(col_w[i]) for i, v in enumerate(row)))

    print(f"\n  总耗时：{elapsed/60:.1f} 分钟")
    print(f"  结果目录：{result_dir}")
    print(f"\n  查看 Pareto 对比图：{os.path.join(result_dir, 'Pareto_Comparison.png')}")
    print(f"  查看详细报告：{os.path.join(result_dir, 'comparison_report.md')}")
    print("=" * 60)


# ── 交互式菜单 ────────────────────────────────────────────────────────────
def interactive_menu() -> dict:
    print("\n" + "=" * 60)
    print("  CCHP 优化实验启动器")
    print("=" * 60)
    print("\n请选择运行模式：\n")
    for i, (key, cfg) in enumerate(PRESETS.items(), 1):
        print(f"  [{i}] {key:8s}  {cfg['desc']}")
    print(f"  [4] custom    自定义参数")
    print()

    while True:
        choice = input("输入编号 (1-4)：").strip()
        if choice in ("1", "2", "3"):
            key = list(PRESETS.keys())[int(choice) - 1]
            cfg = dict(PRESETS[key])
            print(f"\n已选择：{cfg['desc']}")
            _print_config(cfg)
            confirm = input("\n确认运行？(y/n) [y]：").strip().lower()
            if confirm in ("", "y"):
                return cfg
        elif choice == "4":
            return _custom_menu()
        else:
            print("请输入 1-4")


def _custom_menu() -> dict:
    print("\n── 自定义参数 ──────────────────────────────")

    nind = _ask_int("种群规模 nind", default=30, min_val=5, max_val=200)
    maxgen = _ask_int("最大代数 maxgen", default=50, min_val=3, max_val=500)

    print("\n可选方法：")
    for i, m in enumerate(ALL_METHODS, 1):
        print(f"  [{i}] {METHOD_DESC[m]}")
    raw = input("选择方法编号（逗号分隔，如 1,2,5，回车=全选）：").strip()
    if raw == "":
        methods = ALL_METHODS[:]
    else:
        idxs = [int(x.strip()) - 1 for x in raw.split(",") if x.strip().isdigit()]
        methods = [ALL_METHODS[i] for i in idxs if 0 <= i < len(ALL_METHODS)]
        if not methods:
            methods = ["std", "euclidean"]

    inherit = input("是否开启种群继承（euclidean 继承 std）？(y/n) [y]：").strip().lower()
    inherit_population = inherit in ("", "y")

    cfg = {
        "nind": nind,
        "maxgen": maxgen,
        "pool_type": "Process",
        "inherit_population": inherit_population,
        "methods": methods,
    }
    _print_config(cfg)
    confirm = input("\n确认运行？(y/n) [y]：").strip().lower()
    if confirm not in ("", "y"):
        print("已取消。")
        sys.exit(0)
    return cfg


def _ask_int(prompt, default, min_val, max_val):
    while True:
        raw = input(f"{prompt} [{default}]：").strip()
        if raw == "":
            return default
        if raw.isdigit() and min_val <= int(raw) <= max_val:
            return int(raw)
        print(f"  请输入 {min_val}-{max_val} 之间的整数")


def _print_config(cfg: dict):
    print("\n  参数预览：")
    print(f"    种群规模  nind     = {cfg['nind']}")
    print(f"    最大代数  maxgen   = {cfg['maxgen']}")
    print(f"    并行方式           = {cfg['pool_type']}")
    print(f"    种群继承           = {cfg['inherit_population']}")
    print(f"    运行方法           = {cfg['methods']}")
    n = len(cfg["methods"])
    est = cfg["nind"] * cfg["maxgen"] * n * 0.15
    est_str = (f"约 {est:.0f} 秒" if est < 120
               else f"约 {est/60:.0f} 分钟" if est < 3600
               else f"约 {est/3600:.1f} 小时")
    print(f"    预计耗时           ≈ {est_str}（粗略估算）")


# ── 命令行参数解析 ────────────────────────────────────────────────────────
def _generate_result_dir_name(mode=None, case_name="german", carnot=False,
                               nind=None, maxgen=None, methods=None, exp_id=None,
                               unit_lambda=False):
    """
    生成描述性的结果文件夹名称

    格式：{mode/exp}_{case}_{carnot}_{nind}x{maxgen}_{methods}_{timestamp}
    例如：test_german_10x5_std+euclidean_20240317_143022
         exp1_german_50x100_5methods_20240317_143022
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    parts = []

    # 模式/实验标识
    if exp_id is not None:
        parts.append(f"exp{exp_id}")
    elif mode is not None:
        parts.append(mode)
    else:
        parts.append("custom")

    # 案例名称
    parts.append(case_name)

    # 卡诺电池标识
    if carnot:
        parts.append("carnot")

    if unit_lambda:
        parts.append("unitlambda")

    # 参数信息
    if nind is not None and maxgen is not None:
        parts.append(f"{nind}x{maxgen}")

    # 方法信息
    if methods is not None and len(methods) > 0:
        if len(methods) <= 2:
            methods_str = "+".join(methods)
        else:
            methods_str = f"{len(methods)}methods"
        parts.append(methods_str)

    parts.append(timestamp)

    return "_".join(parts)


def parse_args():
    parser = argparse.ArgumentParser(
        description="CCHP 优化实验启动器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  uv run python run.py                                    # 交互式菜单
  uv run python run.py --check                            # 仅环境检查
  uv run python run.py --mode test                        # 测试模式
  uv run python run.py --mode quick                       # 快速模式
  uv run python run.py --mode full                        # 正式模式
  uv run python run.py --mode custom --nind 40 --maxgen 80 --methods std euclidean
  uv run python run.py --exp all --test-run               # 四组实验-测试参数
  uv run python run.py --exp all --quick-run              # 四组实验-快速参数
  uv run python run.py --exp all                          # 四组实验-正式参数
        """,
    )
    parser.add_argument("--mode", choices=["test", "quick", "full", "custom"],
                        help="运行模式（不指定则进入交互菜单）")
    parser.add_argument("--check", action="store_true",
                        help="仅做环境检查，不运行优化")
    parser.add_argument("--nind", type=int, help="种群规模（custom 模式）")
    parser.add_argument("--maxgen", type=int, help="最大代数（custom 模式）")
    parser.add_argument("--methods", nargs="+", choices=ALL_METHODS,
                        help="运行方法列表（custom 模式）")
    parser.add_argument("--no-inherit", action="store_true",
                        help="关闭种群继承")
    parser.add_argument("--skip-check", action="store_true",
                        help="跳过运行前的环境检查")
    parser.add_argument("--case", choices=["german", "songshan_lake"],
                        default="german", help="选择案例（默认德国）")
    parser.add_argument("--carnot", action="store_true",
                        help="启用卡诺电池")
    parser.add_argument("--unit-lambda", action="store_true",
                        help="欧氏匹配度使用等权 λ_e=λ_h=λ_c=1（覆盖卡诺㶲系数）")
    parser.add_argument("--exp", choices=["1", "2", "3", "4", "all"],
                        help="运行论文预设实验（1-4 或 all）")
    parser.add_argument("--test-run", action="store_true",
                        help="实验模式用测试参数（nind=10, maxgen=5）快速验证")
    parser.add_argument("--quick-run", action="store_true",
                        help="实验模式用快速参数（nind=20, maxgen=20）初步验证效果")
    parser.add_argument("--workers", type=int, default=None,
                        help="并行进程数（默认=CPU核心数）")
    return parser.parse_args()


# ── 主入口 ────────────────────────────────────────────────────────────────
def main():
    args = parse_args()

    # 仅检查模式
    if args.check:
        ok = run_checks(verbose=True)
        sys.exit(0 if ok else 1)

    # ── 论文实验模式 ──────────────────────────────────────────────────────
    if args.exp is not None:
        _run_experiments(args)
        return

    # ── 原有模式（test/quick/full/custom/交互）────────────────────────────
    # 确定运行配置
    if args.mode is None:
        cfg = interactive_menu()
    elif args.mode in PRESETS:
        cfg = dict(PRESETS[args.mode])
        print(f"\n模式：{cfg['desc']}")
        _print_config(cfg)
    else:  # custom
        cfg = {
            "nind": args.nind or 30,
            "maxgen": args.maxgen or 50,
            "pool_type": "Process",
            "inherit_population": not args.no_inherit,
            "methods": args.methods or ["std", "euclidean"],
        }
        _print_config(cfg)

    # 运行前环境检查（可跳过）
    if not args.skip_check:
        print()
        ok = run_checks(verbose=True)
        if not ok:
            ans = input("\n环境检查有失败项，仍要继续？(y/n) [n]：").strip().lower()
            if ans != "y":
                print("已取消。")
                sys.exit(1)

    print("\n" + "=" * 60)
    print("启动优化实验...")
    print("=" * 60 + "\n")

    from cchp_gasolution import run_comparative_study
    from case_config import get_case, enable_carnot_battery

    # 加载案例配置
    case_config = get_case(args.case)
    if args.carnot:
        enable_carnot_battery(case_config)
        print(f"案例: {case_config['description']} [卡诺电池已启用]")
    else:
        print(f"案例: {case_config['description']}")
    if args.unit_lambda:
        case_config["lambda_e"] = case_config["lambda_h"] = case_config["lambda_c"] = 1.0
        print("  [unit-lambda] 欧氏匹配度已设为等权 λ_e=λ_h=λ_c=1")

    # 生成描述性结果文件夹名
    mode_label = args.mode or "interactive"
    result_dir_name = _generate_result_dir_name(
        mode=mode_label, case_name=args.case, carnot=args.carnot,
        nind=cfg["nind"], maxgen=cfg["maxgen"], methods=cfg["methods"],
        unit_lambda=args.unit_lambda,
    )

    t0 = time.time()
    try:
        results, result_dir = run_comparative_study(
            nind=cfg["nind"],
            maxgen=cfg["maxgen"],
            pool_type=cfg["pool_type"],
            inherit_population=cfg["inherit_population"],
            methods_to_run=cfg["methods"],
            case_config=case_config,
            num_workers=args.workers,
            result_dir_name=result_dir_name,
        )
        elapsed = time.time() - t0
        print_result_summary(results, elapsed, result_dir)
    except KeyboardInterrupt:
        print("\n\n用户中断。")
        sys.exit(0)
    except Exception:
        print("\n\n优化过程出错：")
        traceback.print_exc()
        sys.exit(1)


def _run_experiments(args):
    """运行论文预设实验"""
    from cchp_gasolution import run_comparative_study
    from case_config import get_case, enable_carnot_battery

    # 确定参数：--test-run 用小参数快速验证，--quick-run 用中等参数，否则用正式参数
    if args.test_run:
        nind, maxgen = 10, 5
        param_desc = "测试参数 (nind=10, maxgen=5)"
        run_level = "test"
    elif args.quick_run:
        nind, maxgen = 20, 20
        param_desc = "快速参数 (nind=20, maxgen=20)"
        run_level = "quick"
    else:
        nind, maxgen = 50, 100
        param_desc = "正式参数 (nind=50, maxgen=100)"
        run_level = "full"

    num_workers = args.workers

    # 确定要跑哪些实验
    if args.exp == "all":
        exp_ids = ["1", "2", "3", "4"]
    else:
        exp_ids = [args.exp]

    # 创建本次运行的共享父文件夹
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    exp_label = "all" if args.exp == "all" else f"exp{args.exp}"
    parent_dir_name = f"{run_level}_{exp_label}_{nind}x{maxgen}_{timestamp}"
    results_root = os.path.join(BASE_DIR, "Results", parent_dir_name)
    os.makedirs(results_root, exist_ok=True)

    print("\n" + "=" * 70)
    print("  论文实验批量运行")
    print("=" * 70)
    print(f"  参数: {param_desc}")
    print(f"  实验: {', '.join(exp_ids)}")
    print(f"  结果汇总目录: {results_root}")
    print()

    for exp_id in exp_ids:
        if exp_id not in EXPERIMENTS:
            continue
        exp = EXPERIMENTS[exp_id]

        # 实验3 特殊处理：先跑无卡诺，再跑有卡诺
        if exp.get("carnot") == "both":
            _run_one_experiment(
                exp_id + "a", exp["name"] + "（无卡诺电池）",
                exp["case"], False, exp["methods"], exp["inherit_population"],
                nind, maxgen, num_workers, parent_dir=results_root,
                unit_lambda=args.unit_lambda,
            )
            _run_one_experiment(
                exp_id + "b", exp["name"] + "（有卡诺电池）",
                exp["case"], True, exp["methods"], exp["inherit_population"],
                nind, maxgen, num_workers, parent_dir=results_root,
                unit_lambda=args.unit_lambda,
            )
        else:
            _run_one_experiment(
                exp_id, exp["name"],
                exp["case"], exp.get("carnot", False),
                exp["methods"], exp["inherit_population"],
                nind, maxgen, num_workers, parent_dir=results_root,
                unit_lambda=args.unit_lambda,
            )

    print("\n" + "=" * 70)
    print("  全部实验完成！")
    print(f"  结果汇总目录: {results_root}")
    print("=" * 70)


def _run_one_experiment(exp_id, name, case_name, carnot, methods,
                        inherit_population, nind, maxgen, num_workers=None, parent_dir=None,
                        unit_lambda=False):
    """运行单组实验"""
    from cchp_gasolution import run_comparative_study
    from case_config import get_case, enable_carnot_battery

    print("\n" + "#" * 70)
    print(f"  [{exp_id}] {name}")
    print("#" * 70)

    case_config = get_case(case_name)
    if carnot:
        enable_carnot_battery(case_config)
    if unit_lambda:
        case_config["lambda_e"] = case_config["lambda_h"] = case_config["lambda_c"] = 1.0
        print("  [unit-lambda] 欧氏匹配度: λ_e=λ_h=λ_c=1")

    cb_str = " + 卡诺电池" if carnot else ""
    print(f"  案例: {case_config['description']}{cb_str}")
    print(f"  方法: {methods}")
    print(f"  参数: nind={nind}, maxgen={maxgen}")

    # 生成描述性子文件夹名
    subfolder_name = _generate_result_dir_name(
        exp_id=exp_id, case_name=case_name, carnot=carnot,
        nind=nind, maxgen=maxgen, methods=methods,
        unit_lambda=unit_lambda,
    )
    if parent_dir is not None:
        result_dir_name = os.path.join(os.path.basename(parent_dir), subfolder_name)
    else:
        result_dir_name = subfolder_name

    t0 = time.time()
    try:
        results, result_dir = run_comparative_study(
            nind=nind,
            maxgen=maxgen,
            pool_type="Process",
            inherit_population=inherit_population,
            methods_to_run=methods,
            case_config=case_config,
            num_workers=num_workers,
            result_dir_name=result_dir_name,
        )
        elapsed = time.time() - t0
        print_result_summary(results, elapsed, result_dir)
    except Exception:
        print(f"\n  [{exp_id}] 出错：")
        traceback.print_exc()
        print(f"  [{exp_id}] 跳过，继续下一组实验\n")


if __name__ == "__main__":
    from multiprocessing import freeze_support
    freeze_support()
    main()
