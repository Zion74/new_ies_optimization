import pandas as pd
import numpy as np
from operation import OperationModel
import os

# Set license file just in case
os.environ["GRB_LICENSE_FILE"] = r"C:\Users\Zion\gurobi.lic"


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


def debug_run():
    print("Loading data...")
    operation_data = pd.read_csv("mergedData.csv")
    operation_list = np.array(operation_data).tolist()

    # Parameters from a failed run
    ppv = 8412.2
    pwt = 4266.4
    pgt = 6008.3
    php = 478.5
    pec = 121.9
    pac = 172.3
    pes = 2985.2
    phs = 3068.1
    pcs = 29.2

    # Pick a typical day (e.g., day 1)
    # In gaproblem.py: time_start = (cluster_medoid - 1) * 24
    # Let's assume cluster_medoid is 1
    time_start = 0
    time_step = 24

    ele_load = [0] * time_step
    heat_load = [0] * time_step
    cool_load = [0] * time_step
    solar_radiation_list = [0] * time_step
    wind_speed_list = [0] * time_step
    temperature_list = [0] * time_step

    ele_price = [0.1598 for _ in range(time_step)]
    gas_price = [0.0286 for _ in range(time_step)]

    for t in range(time_start, time_start + time_step):
        ele_load[t % 24] = operation_list[t][0]
        heat_load[t % 24] = operation_list[t][1]
        cool_load[t % 24] = operation_list[t][2]
        solar_radiation_list[t % 24] = operation_list[t][3]
        wind_speed_list[t % 24] = operation_list[t][4]
        temperature_list[t % 24] = operation_list[t][5]

    pv_output = cal_solar_output(solar_radiation_list, temperature_list, ppv)
    wt_output = cal_wind_output(wind_speed_list, pwt)

    print("Initializing OperationModel...")
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

    print("Starting optimization...")
    try:
        operation_model.optimise()
        print("Optimization finished.")

        obj_val = operation_model.get_objective_value()
        print(f"Objective value: {obj_val}")

        comp_results = operation_model.get_complementary_results()
        print("Complementary results keys:", comp_results.keys())

        # Inspect raw results for grid
        results = operation_model.energy_system.results["main"]
        import oemof.solph as solph

        node = solph.views.node(results, "grid")
        print("\nGrid sequences head:")
        print(node["sequences"].head())
        print("\nGrid sequences tail:")
        print(node["sequences"].tail())
        print("\nGrid sequences info:")
        print(node["sequences"].info())
        print("\nGrid sequences values:")
        print(node["sequences"].values)

        for k, v in comp_results.items():
            print(f"{k}: {v[:5]}...")  # Print first 5 elements
            if np.any(np.isnan(v)):
                print(f"!!! NaN found in {k} !!!")
                print(f"Full list for {k}: {v}")

    except Exception as e:
        print(f"Optimization failed with exception: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    debug_run()
