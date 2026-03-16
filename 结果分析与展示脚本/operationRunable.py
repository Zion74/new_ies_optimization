import pandas as pd
import numpy as np
import os
import matplotlib.pyplot as plt
from operation import OperationModel

# Set license file just in case
os.environ["GRB_LICENSE_FILE"] = r"C:\gurobi\gurobi.lic"


def cal_solar_output(solar_radiation_list, temperature_list, ppv):
    return [
        ppv * 0.9 * r / 1000 * (1 - 0.0035 * (t - 25))
        for r, t in zip(solar_radiation_list, temperature_list)
    ]


def cal_wind_output(wind_speed_list, pwt):
    ret = [0 for _ in range(len(wind_speed_list))]
    for i in range(len(wind_speed_list)):
        w = wind_speed_list[i]
        if 2.5 <= w < 9:
            ret[i] = (w**3 - 2.5**3) / (9**3 - 2.5**3) * pwt
        elif 9 <= w < 25:
            ret[i] = pwt
    return ret


import glob


def run_simulation(
    ppv,
    pwt,
    pgt,
    php,
    pec,
    pac,
    pes,
    phs,
    pcs,
    output_dir=None,
    plot_bus="electricity bus",
):
    # 重定向输出到文件（如果指定了输出目录）
    log_file = None
    if output_dir:
        log_path = os.path.join(output_dir, "Simulation_Result_Log.txt")
        log_file = open(log_path, "w", encoding="utf-8")

    def log_print(msg):
        print(msg)
        if log_file:
            log_file.write(msg + "\n")

    log_print(f"\nRunning simulation with configuration:")
    log_print(
        f"PV={ppv:.2f}, WT={pwt:.2f}, GT={pgt:.2f}, HP={php:.2f}, EC={pec:.2f}, AC={pac:.2f}, ES={pes:.2f}, HS={phs:.2f}, CS={pcs:.2f}"
    )

    operation_data = pd.read_csv("mergedData.csv")
    operation_list = np.array(operation_data).tolist()
    typical_days = dict()
    typical_data = pd.read_excel("typicalDayData.xlsx")
    typical_day_id = typical_data["typicalDayId"]
    days_str = typical_data["days"]
    for i in range(len(typical_day_id)):
        days_list = list(map(int, days_str[i].split(",")))
        typical_days[typical_day_id[i]] = days_list

    net_ele_load = [0 for _ in range(8760)]  # 电净负荷
    net_heat_load = [0 for _ in range(8760)]  # 热净负荷
    net_cool_load = [0 for _ in range(8760)]  # 冷净负荷
    time_step = 24
    ele_price = [0.1598 for _ in range(time_step)]
    gas_price = [0.0286 for _ in range(time_step)]
    ele_load = [0 for _ in range(time_step)]
    heat_load = [0 for _ in range(time_step)]
    cool_load = [0 for _ in range(time_step)]
    solar_radiation_list = [0 for _ in range(time_step)]
    wind_speed_list = [0 for _ in range(time_step)]
    temperature_list = [0 for _ in range(time_step)]

    total_oc = 0

    for cluster_medoid in typical_days.keys():
        time_start = (cluster_medoid - 1) * 24
        # 下层模型参数设置
        for t in range(time_start, time_start + time_step):
            ele_load[t % 24] = operation_list[t][0]
            heat_load[t % 24] = operation_list[t][1]
            cool_load[t % 24] = operation_list[t][2]
            solar_radiation_list[t % 24] = operation_list[t][3]
            wind_speed_list[t % 24] = operation_list[t][4]
            temperature_list[t % 24] = operation_list[t][5]
        pv_output = cal_solar_output(solar_radiation_list, temperature_list, ppv)
        wt_output = cal_wind_output(wind_speed_list, pwt)
        # 底层模型初始化及优化
        operation_model = OperationModel(
            "01/01/2019",
            time_step,
            ele_price,
            gas_price,
            ele_load,
            heat_load,
            cool_load,
            wt_output,
            pv_output,
            pgt,
            php,
            pec,
            pac,
            pes,
            phs,
            pcs,
        )
        try:
            # 优化并获取结果
            operation_model.optimise()
            obj_val = operation_model.get_objective_value()
            total_oc += obj_val * len(typical_days[cluster_medoid])

            complementary_results = operation_model.get_complementary_results()

            # 仅对第一个典型日进行绘图展示，避免弹出太多窗口
            if cluster_medoid == list(typical_days.keys())[0]:
                log_print(
                    f"Plotting results for typical day cluster {cluster_medoid}..."
                )
                save_path = None
                if output_dir:
                    save_path = os.path.join(
                        output_dir, f"Simulation_Plot_Cluster_{cluster_medoid}.png"
                    )
                operation_model.result_process(plot_bus, save_path=save_path)

        except Exception as e:
            log_print(f"Optimization failed for cluster {cluster_medoid}: {e}")
            break

        for d in typical_days[cluster_medoid]:
            start_index = (d - 1) * 24
            for i in range(24):
                # 使用修正后的净负荷计算逻辑
                net_ele_load[start_index + i] = (
                    complementary_results["grid"][i]
                    - complementary_results["electricity overflow"][i]
                )
                net_heat_load[start_index + i] = (
                    complementary_results["heat source"][i]
                    - complementary_results["heat overflow"][i]
                )
                net_cool_load[start_index + i] = (
                    complementary_results["cool source"][i]
                    - complementary_results["cool overflow"][i]
                )

    log_print(f"Total Operating Cost: {total_oc:,.2f}")
    log_print(
        f"Net Load Std: Ele={np.std(net_ele_load):.4f}, Heat={np.std(net_heat_load):.4f}, Cool={np.std(net_cool_load):.4f}"
    )

    if log_file:
        log_file.close()
        print(f"Simulation log saved to {log_path}")


if __name__ == "__main__":
    # 查找最新的 Result 文件夹
    result_dirs = glob.glob("Result_*")
    # 按修改时间排序，最新的在最后
    result_dirs.sort(key=os.path.getmtime)

    target_dir = None
    pareto_file = None

    if result_dirs:
        latest_dir = result_dirs[-1]
        potential_file = os.path.join(latest_dir, "Pareto_Front.csv")
        if os.path.exists(potential_file):
            target_dir = latest_dir
            pareto_file = potential_file
            print(f"Found latest result directory: {target_dir}")

    # 如果没找到带时间戳的文件夹，尝试找根目录的（兼容旧版）
    if not pareto_file and os.path.exists("Pareto_Front.csv"):
        pareto_file = "Pareto_Front.csv"
        target_dir = "."  # 当前目录
        print("Using Pareto_Front.csv from current directory.")

    if pareto_file:
        print(f"Loading solutions from {pareto_file}...")
        df = pd.read_csv(pareto_file)

        # 默认选择经济成本最低的方案
        best_eco_idx = df["Economic Cost"].idxmin()
        solution = df.loc[best_eco_idx]

        print("Selected Solution (Minimum Economic Cost):")
        print(solution)

        run_simulation(
            ppv=solution["PV"],
            pwt=solution["WT"],
            pgt=solution["GT"],
            php=solution["HP"],
            pec=solution["EC"],
            pac=solution["AC"],
            pes=solution["ES"],
            phs=solution["HS"],
            pcs=solution["CS"],
            output_dir=target_dir,  # 将结果保存回同一个文件夹
        )
    else:
        print(f"No Pareto_Front.csv found. Using default hardcoded values.")
        ppv = 1710.86  # 光伏额定功率
        pwt = 1648.98  # 风电额定功率
        pgt = 2217.91  # 燃气轮机额定功率
        php = 2.79  # 电热泵额定功率
        pec = 5.17  # 电制冷额定功率
        pac = 305.72  # 吸收式制冷额定功率
        pes = 0.04  # 电储能额定功率
        phs = 2351.50  # 热储能额定功率
        pcs = 400.82  # 冷储能额定功率

        run_simulation(ppv, pwt, pgt, php, pec, pac, pes, phs, pcs)
