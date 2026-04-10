import gurobipy as gp
from gurobipy import GRB

def test_wls_connection():
    print("--- 开始测试 Gurobi WLS 连接 ---")
    try:
        # 尝试创建一个默认环境
        # Gurobi 会自动读取默认路径下的 gurobi.lic 文件
        # 或者读取环境变量 GRB_LICENSE_FILE 指向的文件
        with gp.Env(empty=True) as env:
            # 如果你是硬编码在代码里（不推荐，但有时用于测试），可以在这里 setParam
            # env.setParam('WLSACCESSID', '你的ID')
            # env.setParam('WLSSECRET', '你的SECRET')
            # env.setParam('LICENSEID', 你的LICENSE_ID)
            
            env.start() # 这一步真正触发联网验证
            
        print("\n[成功] Gurobi 环境启动成功！")
        
        # 简单创建一个极小的模型确保求解器能跑
        m = gp.Model("test")
        x = m.addVar(name="x")
        y = m.addVar(name="y")
        m.setObjective(x + y, GRB.MAXIMIZE)
        m.addConstr(x + y <= 1)
        m.optimize()
        
        print(f"\n[成功] 简单模型求解完成，目标值: {m.objVal}")

    except gp.GurobiError as e:
        print(f"\n[失败] Gurobi 报错 (错误码 {e.errno}): {e}")
        print("常见原因：")
        print("1. 无法连接互联网 (WLS 必须联网)")
        print("2. gurobi.lic 文件路径不对或内容错误")
        print("3. WLS License 已过期或达到并发上限")
    except Exception as e:
        print(f"\n[失败] 系统报错: {e}")

if __name__ == "__main__":
    test_wls_connection()