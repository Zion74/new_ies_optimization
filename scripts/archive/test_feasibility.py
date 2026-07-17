# -*- coding: utf-8 -*-
"""
可行性测试脚本
测试内容：
  1. Python 环境与依赖
  2. 求解器（Gurobi / GLPK）
  3. 数据文件
  4. OperationModel 单次优化
  5. CCHPProblem 初始化 + 单个体目标函数计算
  6. Python K-Medoids 聚类（kmeans_clustering.py）
  7. MATLAB 可用性（仅检测，不运行 kmedoids）
"""

import os
import sys
import time
import subprocess

os.environ["GRB_LICENSE_FILE"] = r"C:\Users\ikun\gurobi.lic"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = "[PASS]"
FAIL = "[FAIL]"
SKIP = "[SKIP]"

results = []

def check(name, fn):
    try:
        msg = fn()
        results.append((PASS, name, msg or ""))
        print(f"{PASS} {name}" + (f"  →  {msg}" if msg else ""))
    except Exception as e:
        results.append((FAIL, name, str(e)))
        print(f"{FAIL} {name}  →  {e}")

# ─────────────────────────────────────────────
# 1. 基础依赖导入
# ─────────────────────────────────────────────
print("\n=== 1. 依赖导入 ===")

def test_imports():
    import numpy, pandas, matplotlib, geatpy, oemof.solph, pyomo.environ
    return (f"numpy={numpy.__version__}  pandas={pandas.__version__}  "
            f"geatpy={geatpy.__version__}  oemof.solph={oemof.solph.__version__}")
check("核心包导入", test_imports)

# ─────────────────────────────────────────────
# 2. 求解器
# ─────────────────────────────────────────────
print("\n=== 2. 求解器 ===")

def test_glpk():
    import pyomo.environ as pyo
    from pyomo.opt import SolverFactory
    s = SolverFactory("glpk")
    assert s.available(), "glpk not available"
    return "available"
check("GLPK", test_glpk)

def test_gurobi():
    import pyomo.environ as pyo
    from pyomo.opt import SolverFactory
    s = SolverFactory("gurobi")
    assert s.available(), "gurobi not available"
    return "available"
check("Gurobi", test_gurobi)

# ─────────────────────────────────────────────
# 3. 数据文件
# ─────────────────────────────────────────────
print("\n=== 3. 数据文件 ===")

base = os.path.dirname(os.path.abspath(__file__))

def test_csv():
    import pandas as pd
    df = pd.read_csv(os.path.join(base, "mergedData.csv"))
    return f"{len(df)} 行 × {len(df.columns)} 列"
check("mergedData.csv", test_csv)

def test_xlsx():
    import pandas as pd
    df = pd.read_excel(os.path.join(base, "typicalDayData.xlsx"), engine="openpyxl")
    return f"{len(df)} 行 × {len(df.columns)} 列"
check("typicalDayData.xlsx", test_xlsx)

def test_opt_xlsx():
    import pandas as pd
    df = pd.read_excel(os.path.join(base, "optimizationData.xlsx"), engine="openpyxl")
    return f"{len(df)} 行 × {len(df.columns)} 列"
check("optimizationData.xlsx", test_opt_xlsx)

# ─────────────────────────────────────────────
# 4. OperationModel 单次优化
# ─────────────────────────────────────────────
print("\n=== 4. OperationModel 单次优化 ===")

def test_operation_model():
    from operation import OperationModel
    T = 24
    model = OperationModel(
        "01/01/2019", T,
        [0.0025] * T, [0.0286] * T,
        [100.0] * T, [80.0] * T, [50.0] * T,
        [30.0] * T, [20.0] * T,
        500, 200, 100, 100, 500, 200, 100,
    )
    t0 = time.time()
    model.optimise()
    elapsed = time.time() - t0
    obj = model.get_objective_value()
    assert obj is not None and obj > 0
    res = model.get_complementary_results()
    assert "grid" in res and len(res["grid"]) == T
    return f"目标值={obj:.4f}  耗时={elapsed:.2f}s"
check("OperationModel 优化", test_operation_model)

# ─────────────────────────────────────────────
# 5. CCHPProblem 初始化 + 单个体评估
# ─────────────────────────────────────────────
print("\n=== 5. CCHPProblem 单个体评估 ===")

def test_cchp_problem():
    import numpy as np
    from cchp_gaproblem import CCHPProblem, sub_aim_func_cchp
    import pandas as pd

    problem = CCHPProblem("Thread", method="euclidean")

    # 构造一个合理的个体：[ppv, pwt, pgt, php, pec, pac, pes, phs, pcs]
    vars_row = np.array([[2000, 1500, 1000, 500, 200, 200, 3000, 1000, 500]])

    args = (0, vars_row, problem.operation_list, problem.typical_days, 1, "euclidean")
    t0 = time.time()
    result = sub_aim_func_cchp(args)
    elapsed = time.time() - t0

    problem.kill_pool()
    assert len(result) == 2
    eco, match = result
    assert eco < 1e9, f"经济目标异常: {eco}"
    return f"经济={eco:,.0f}€  匹配={match:.2f}  耗时={elapsed:.1f}s"
check("CCHPProblem 单个体", test_cchp_problem)

# ─────────────────────────────────────────────
# 6. Python K-Medoids 聚类
# ─────────────────────────────────────────────
print("\n=== 6. Python K-Medoids 聚类 ===")

def test_python_clustering():
    from kmeans_clustering import run_clustering
    import pandas as pd
    t0 = time.time()
    df = run_clustering(
        csv_path=os.path.join(base, "mergedData.csv"),
        output_path=os.path.join(base, "typicalDayData.xlsx"),
    )
    elapsed = time.time() - t0
    assert len(df) == 14, f"期望14个典型日，实际{len(df)}"
    assert df["weight"].sum() == 365, f"天数之和应为365，实际{df['weight'].sum()}"
    return f"14个典型日，覆盖365天，耗时={elapsed:.1f}s，已更新 typicalDayData.xlsx"
check("Python K-Medoids (kmeans_clustering.py)", test_python_clustering)

# ─────────────────────────────────────────────
# 7. MATLAB 可用性（仅检测）
# ─────────────────────────────────────────────
print("\n=== 7. MATLAB ===")

MATLAB_EXE = r"C:\Program Files\MATLAB\R2025b\bin\matlab.exe"

def test_matlab_available():
    assert os.path.exists(MATLAB_EXE), f"未找到: {MATLAB_EXE}"
    r = subprocess.run(
        [MATLAB_EXE, "-batch", "disp('matlab_ok')"],
        capture_output=True, text=True, timeout=60
    )
    assert "matlab_ok" in r.stdout, f"stdout={r.stdout!r}  stderr={r.stderr!r}"
    return "MATLAB R2025b 启动正常（聚类已由 Python 替代，无需 Statistics Toolbox）"
check("MATLAB 可用性", test_matlab_available)

# ─────────────────────────────────────────────
# 汇总
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("测试汇总")
print("=" * 60)
passed = sum(1 for r in results if r[0] == PASS)
failed = sum(1 for r in results if r[0] == FAIL)
for status, name, msg in results:
    print(f"  {status}  {name}")
print(f"\n共 {len(results)} 项：{passed} 通过，{failed} 失败")
if failed == 0:
    print("\n项目可行性验证通过，可以运行主程序：")
    print("  uv run python cchp_gasolution.py")
else:
    print("\n存在失败项，请根据上方错误信息修复后重试。")
