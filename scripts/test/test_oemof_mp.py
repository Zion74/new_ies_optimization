import multiprocessing as mp
import os, time, warnings

def worker(idx):
    os.environ['GRB_LICENSE_FILE'] = r'C:\Users\ikun\gurobi.lic'
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
    print("测试 2 个并发子进程...")
    ctx = mp.get_context('spawn')
    with ctx.Pool(2) as pool:
        results = pool.map(worker, [0, 1])
    for r in results:
        print(r)
    print("完成")
