import multiprocessing as mp
import os, time

def worker(_):
    os.environ['GRB_LICENSE_FILE'] = r'C:\Users\ikun\gurobi.lic'
    t0 = time.time()
    import gurobipy as gp
    env = gp.Env()
    m = gp.Model(env=env)
    x = m.addVar()
    m.setObjective(x)
    m.addConstr(x >= 1)
    m.optimize()
    val = x.X
    env.dispose()
    return ('ok', val, round(time.time()-t0, 1))

if __name__ == '__main__':
    ctx = mp.get_context('spawn')
    with ctx.Pool(2) as pool:
        results = pool.map(worker, [None, None])
    print(results)
