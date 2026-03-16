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


def verify_scheme_30():
    print("Loading data...")
    operation_data = pd.read_csv("mergedData.csv")
    operation_list = np.array(operation_data).tolist()

    typical_days = dict()
    typical_data = pd.read_excel("typicalDayData.xlsx")
    typical_day_id = typical_data["typicalDayId"]
    days_str = typical_data["days"]
    for i in range(len(typical_day_id)):
        days_list = list(map(int, days_str[i].split(",")))
        typical_days[typical_day_id[i]] = days_list

    # User provided values for Scheme 30
    ppv = 5614.6
    pwt = 3075.0
    pgt = 8239.1
    php = 2767.7
    pec = 447.9
    pac = 612.7
    pes = 15652.5
    phs = 727.3
    pcs = 1072.1

    print(f"Verifying Scheme 30 with:")
    print(
        f"PV={ppv}, WT={pwt}, GT={pgt}, HP={php}, EC={pec}, AC={pac}, ES={pes}, HS={phs}, CS={pcs}"
    )

    # 1. Calculate Investment Cost (Fixed part)
    inv_cost = (
        76.44188371 * ppv
        + 110.4233218 * pwt
        + 50.32074101 * pgt
        + 21.21527903 * php
        + 22.85563566 * pec
        + 21.81674313 * pac
        + 35.11456751 * pes
        + 1.689590459 * (phs + pcs)
        + 520 * (phs > 0.1)
        + 520 * (pcs > 0.1)
    )

    print(f"\n[Calculated Investment Cost]: {inv_cost:,.2f}")

    # 2. Run Simulation for Operating Cost and Matching Degree
    oc = 0
    net_ele_load = [0 for _ in range(8760)]
    net_heat_load = [0 for _ in range(8760)]
    net_cool_load = [0 for _ in range(8760)]

    time_step = 24
    ele_price = [0.1598 for _ in range(time_step)]
    gas_price = [0.0286 for _ in range(time_step)]

    ele_load = [0 for _ in range(time_step)]
    heat_load = [0 for _ in range(time_step)]
    cool_load = [0 for _ in range(time_step)]
    solar_radiation_list = [0 for _ in range(time_step)]
    wind_speed_list = [0 for _ in range(time_step)]
    temperature_list = [0 for _ in range(time_step)]

    print("\nRunning simulation for typical days...")
    for cluster_medoid in typical_days.keys():
        time_start = (cluster_medoid - 1) * 24
        for t in range(time_start, time_start + time_step):
            ele_load[t % 24] = operation_list[t][0]
            heat_load[t % 24] = operation_list[t][1]
            cool_load[t % 24] = operation_list[t][2]
            solar_radiation_list[t % 24] = operation_list[t][3]
            wind_speed_list[t % 24] = operation_list[t][4]
            temperature_list[t % 24] = operation_list[t][5]

        pv_output = cal_solar_output(solar_radiation_list, temperature_list, ppv)
        wt_output = cal_wind_output(wind_speed_list, pwt)

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
            operation_model.optimise()
            obj_val = operation_model.get_objective_value()

            # Accumulate Operating Cost
            days_count = len(typical_days[cluster_medoid])
            oc += obj_val * days_count

            complementary_results = operation_model.get_complementary_results()

            # Fill net loads for all represented days
            for d in typical_days[cluster_medoid]:
                start_index = (d - 1) * 24
                for k in range(24):
                    # Using the NEW logic
                    net_ele_load[start_index + k] = (
                        complementary_results["grid"][k]
                        - complementary_results["electricity overflow"][k]
                    )
                    net_heat_load[start_index + k] = (
                        complementary_results["heat source"][k]
                        - complementary_results["heat overflow"][k]
                    )
                    net_cool_load[start_index + k] = (
                        complementary_results["cool source"][k]
                        - complementary_results["cool overflow"][k]
                    )

        except Exception as e:
            print(f"Optimization failed for cluster {cluster_medoid}: {e}")
            return

    print(f"\n[Calculated Operating Cost (oc)]: {oc:,.2f}")

    total_economic_cost = inv_cost + oc
    print(f"[Total Economic Cost]: {total_economic_cost:,.2f}")

    std_ele = np.std(net_ele_load)
    std_heat = np.std(net_heat_load)
    std_cool = np.std(net_cool_load)

    print(
        f"\n[Net Load Std Dev]: Ele={std_ele:.4f}, Heat={std_heat:.4f}, Cool={std_cool:.4f}"
    )
    total_matching = std_ele + std_heat + std_cool
    print(f"[Total Source-Load Matching Degree]: {total_matching:.4f}")


if __name__ == "__main__":
    verify_scheme_30()
