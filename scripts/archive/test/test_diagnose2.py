"""
诊断：找出第一次 map 调用卡死的位置
"""
import os, sys, time
import numpy as np
sys.path.insert(0, '.')

os.environ['GRB_LICENSE_FILE'] = r'C:\Users\ikun\gurobi.lic'
from cchp_gasolution import run_comparative_study
from case_config import get_case
from cchp_gaproblem import CCHPProblem
import geatpy as ea

case_config = get_case('german')

print("创建 CCHPProblem...", flush=True)
problem = CCHPProblem('Process', method='std', case_config=case_config)
print("CCHPProblem 创建成功", flush=True)

# 创建一个小种群
Encoding = "RI"
Field = ea.crtfld(Encoding, problem.varTypes, problem.ranges, problem.borders)
population = ea.Population(Encoding, Field, 4)  # 只用4个个体
population.initChrom()

print("开始 aimFunc...", flush=True)
t0 = time.time()
problem.aimFunc(population)
print(f"aimFunc 完成 ({time.time()-t0:.1f}s)", flush=True)
print("ObjV:", population.ObjV[:2])

problem.kill_pool()
print("完成", flush=True)
