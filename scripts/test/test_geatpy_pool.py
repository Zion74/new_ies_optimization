import os, time, warnings
import multiprocessing as mp
from multiprocessing import Pool as ProcessPool

def _init_worker():
    os.environ['GRB_LICENSE_FILE'] = r'C:\Users\ikun\gurobi.lic'

def worker(idx):
    warnings.filterwarnings('ignore')
    t0 = time.time()
    from operation import OperationModel
    T = 24
    m = OperationModel('01/01/2019', T, [0.0025]*T, [0.0286]*T,
        [100.]*T, [80.]*T, [50.]*T, [30.]*T, [20.]*T,
        500, 200, 100, 100, 500, 200, 100)
    m.optimise()
    val = m.get_objective_value()
    return (idx, 'ok', round(val, 2), round(time.time()-t0, 1))

if __name__ == '__main__':
    num_cores = mp.cpu_count()
    print(f"使用 {num_cores} 核心")
    pool = ProcessPool(num_cores, initializer=_init_worker)
    print("进程池创建成功，开始 map...")
    results = pool.map(worker, list(range(4)))
    pool.close()
    for r in results:
        print(r)
    print("完成")
