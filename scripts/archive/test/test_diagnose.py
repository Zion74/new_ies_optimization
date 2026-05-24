"""
诊断：找出 run.py 卡死的确切位置
"""
import os, sys, time
sys.path.insert(0, '.')

print("Step 1: import cchp_gasolution...", flush=True)
os.environ['GRB_LICENSE_FILE'] = r'C:\Users\ikun\gurobi.lic'
from cchp_gasolution import run_comparative_study
print("Step 1: OK", flush=True)

print("Step 2: import case_config...", flush=True)
from case_config import get_case
case_config = get_case('german')
print("Step 2: OK", flush=True)

print("Step 3: import CCHPProblem...", flush=True)
from cchp_gaproblem import CCHPProblem
print("Step 3: OK", flush=True)

print("Step 4: create CCHPProblem with Process pool...", flush=True)
t0 = time.time()
problem = CCHPProblem('Process', method='std', case_config=case_config)
print(f"Step 4: OK ({time.time()-t0:.1f}s)", flush=True)

print("Step 5: kill pool...", flush=True)
problem.kill_pool()
print("Step 5: OK", flush=True)
