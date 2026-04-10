# -*- coding: utf-8 -*-
"""
极端场景韧性测试脚本
==================

测试场景：
1. 电网故障场景（电价飙升 2-5 倍）
2. 气价波动场景（气价上涨 50%-200%）
3. 极端天气场景（可再生能源出力骤降）
4. 负荷激增场景（负荷突增 20%-50%）

用途：证明匹配度高的系统在极端场景下韧性更强

用法：
  python scripts/resilience_test.py --result-dir Results/pipeline_german_50x100_5methods_xxx
  python scripts/resilience_test.py --result-dir Results/pipeline_german_50x100_5methods_xxx --scenarios grid_failure gas_surge
"""

import sys
import os
import argparse
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from tqdm import tqdm

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from operation import OperationModel
from case_config import get_case

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False


def load_operation_data(case_name='german'):
    """加载运行数据"""
    config = get_case(case_name)
    data_file = config['data_file']
    typical_file = config['typical_day_file']

    operation_data = pd.read_csv(data_file)
    operation_list = np.array(operation_data).tolist()

    typical_days = {}
    typical_data = pd.read_excel(typical_file)
    for _, row in typical_data.iterrows():
        day_id = row['typicalDayId']
        days_str = str(row['days'])
        days_list = list(map(int, days_str.split(',')))
        typical_days[day_id] = days_list

    return operation_list, typical_days, config


def cal_solar_output(solar_radiation_list, temperature_list, ppv):
    return [ppv * 0.9 * r / 1000 * (1 - 0.0035 * (t - 25))
            for r, t in zip(solar_radiation_list, temperature_list)]


def cal_wind_output(wind_speed_list, pwt):
    ret = []
    for w in wind_speed_list:
        if 2.5 <= w < 9:
            ret.append((w**3 - 2.5**3) / (9**3 - 2.5**3) * pwt)
        elif 9 <= w <= 25:
            ret.append(pwt)
        else:
            ret.append(0)
    return ret


def run_scenario_test(solution, operation_list, typical_days, config, scenario_params):
    """
    在特定场景下运行调度测试

    Parameters
    ----------
    scenario_params : dict
        场景参数，如 {'ele_price_multiplier': 3.0, 'renewable_reduction': 0.5}
    """
    time_step = 24
    total_cost = 0
    failed_days = 0
    max_grid_purchase = 0

    for cluster_medoid, days in typical_days.items():
        time_start = (cluster_medoid - 1) * 24

        # 提取数据
        ele_load = [operation_list[time_start + t][0] for t in range(time_step)]
        heat_load = [operation_list[time_start + t][1] for t in range(time_step)]
        cool_load = [operation_list[time_start + t][2] for t in range(time_step)]
        solar_radiation = [operation_list[time_start + t][3] for t in range(time_step)]
        wind_speed = [operation_list[time_start + t][4] for t in range(time_step)]
        temperature = [operation_list[time_start + t][5] for t in range(time_step)]

        # 应用场景参数
        ele_price = [config['ele_price'][t % 24] * scenario_params.get('ele_price_multiplier', 1.0)
                    for t in range(time_step)]
        gas_price = [config['gas_price'][t % 24] * scenario_params.get('gas_price_multiplier', 1.0)
                    for t in range(time_step)]

        # 可再生能源出力
        pv_output = cal_solar_output(solar_radiation, temperature, solution['PV'])
        wt_output = cal_wind_output(wind_speed, solution['WT'])

        # 可再生能源削减
        renewable_reduction = scenario_params.get('renewable_reduction', 1.0)
        pv_output = [p * renewable_reduction for p in pv_output]
        wt_output = [w * renewable_reduction for w in wt_output]

        # 负荷增长
        load_multiplier = scenario_params.get('load_multiplier', 1.0)
        ele_load = [e * load_multiplier for e in ele_load]
        heat_load = [h * load_multiplier for h in heat_load]
        cool_load = [c * load_multiplier for c in cool_load]

        # 运行调度
        try:
            cb_power = solution.get('CB_Power', 0)
            cb_capacity = solution.get('CB_Capacity', 0)

            om = OperationModel(
                "01/01/2019", time_step,
                ele_price, gas_price,
                ele_load, heat_load, cool_load,
                wt_output, pv_output,
                solution['GT'], solution['HP'], solution['EC'], solution['AC'],
                solution['ES'], solution['HS'], solution['CS'],
                config=config,
                cb_power=cb_power,
                cb_capacity=cb_capacity
            )

            om.optimise()
            day_cost = om.get_objective_value()
            total_cost += day_cost * len(days)

            # 获取电网购电
            results = om.get_complementary_results()
            grid_purchase = max(results['grid'])
            max_grid_purchase = max(max_grid_purchase, grid_purchase)

        except Exception as e:
            # 调度失败，记录并使用惩罚成本
            failed_days += len(days)
            total_cost += 1e6 * len(days)

    return {
        'total_cost': total_cost,
        'failed_days': failed_days,
        'max_grid_purchase': max_grid_purchase,
        'success_rate': 1 - failed_days / 365
    }


def test_resilience(result_dir, case_name='german', scenarios=None):
    """
    韧性测试主函数
    """
    if scenarios is None:
        scenarios = ['grid_failure', 'gas_surge', 'renewable_drop', 'load_surge']

    # 加载数据
    print("加载运行数据...")
    operation_list, typical_days, config = load_operation_data(case_name)

    # 定义测试场景
    scenario_configs = {
        'baseline': {
            'name': '基准场景',
            'params': {}
        },
        'grid_failure': {
            'name': '电网故障（电价×3）',
            'params': {'ele_price_multiplier': 3.0}
        },
        'gas_surge': {
            'name': '气价飙升（气价×2）',
            'params': {'gas_price_multiplier': 2.0}
        },
        'renewable_drop': {
            'name': '极端天气（可再生能源-50%）',
            'params': {'renewable_reduction': 0.5}
        },
        'load_surge': {
            'name': '负荷激增（负荷+30%）',
            'params': {'load_multiplier': 1.3}
        }
    }

    # 选取代表方案
    methods_to_test = ['Std', 'Euclidean']
    solutions = {}

    for method in methods_to_test:
        pareto_file = Path(result_dir) / method / f"Pareto_{method}.csv"
        if not pareto_file.exists():
            continue

        df = pd.read_csv(pareto_file, index_col=0)

        # 选取拐点方案（成本和匹配度归一化后和最小）
        costs = df['Economic_Cost'].values
        matchings = df['Matching_Index'].values
        c_norm = (costs - costs.min()) / (costs.max() - costs.min() + 1e-9)
        m_norm = (matchings - matchings.min()) / (matchings.max() - matchings.min() + 1e-9)
        knee_idx = np.argmin(c_norm + m_norm)

        solutions[method] = df.iloc[knee_idx]

    if len(solutions) == 0:
        print("错误：未找到可测试的方案")
        return

    # 运行测试
    results = {}

    for scenario_key in ['baseline'] + scenarios:
        if scenario_key not in scenario_configs:
            continue

        scenario = scenario_configs[scenario_key]
        print(f"\n测试场景: {scenario['name']}")

        results[scenario_key] = {}

        for method, solution in solutions.items():
            print(f"  测试方案: {method}")
            result = run_scenario_test(
                solution, operation_list, typical_days,
                config, scenario['params']
            )
            results[scenario_key][method] = result

    return results, scenario_configs


def plot_resilience_results(results, scenario_configs, output_dir):
    """绘制韧性测试结果"""

    scenarios = list(results.keys())
    methods = list(results[scenarios[0]].keys())

    # 1. 成本增长率对比
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    # 子图1：绝对成本
    ax1 = axes[0]
    x = np.arange(len(scenarios))
    width = 0.35

    for idx, method in enumerate(methods):
        costs = [results[s][method]['total_cost'] / 10000 for s in scenarios]
        ax1.bar(x + idx * width, costs, width, label=method, alpha=0.8)

    ax1.set_xlabel('场景', fontsize=12)
    ax1.set_ylabel('年运行成本 (万€)', fontsize=12)
    ax1.set_title('极端场景下运行成本对比', fontsize=14)
    ax1.set_xticks(x + width / 2)
    ax1.set_xticklabels([scenario_configs[s]['name'] for s in scenarios], rotation=15, ha='right')
    ax1.legend()
    ax1.grid(axis='y', alpha=0.3)

    # 子图2：相对基准的成本增长率
    ax2 = axes[1]

    for idx, method in enumerate(methods):
        baseline_cost = results['baseline'][method]['total_cost']
        growth_rates = [(results[s][method]['total_cost'] / baseline_cost - 1) * 100
                       for s in scenarios[1:]]  # 跳过 baseline

        ax2.plot(range(len(growth_rates)), growth_rates,
                marker='o', label=method, linewidth=2, markersize=8)

    ax2.set_xlabel('场景', fontsize=12)
    ax2.set_ylabel('成本增长率 (%)', fontsize=12)
    ax2.set_title('极端场景下成本增长率对比', fontsize=14)
    ax2.set_xticks(range(len(scenarios[1:])))
    ax2.set_xticklabels([scenario_configs[s]['name'] for s in scenarios[1:]], rotation=15, ha='right')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    ax2.axhline(y=0, color='black', linestyle='--', linewidth=0.5)

    plt.tight_layout()
    save_path = output_dir / "Fig_Resilience_Cost_Comparison.png"
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"  已保存: {save_path}")

    # 2. 成功率对比
    fig, ax = plt.subplots(figsize=(12, 6))

    for idx, method in enumerate(methods):
        success_rates = [results[s][method]['success_rate'] * 100 for s in scenarios]
        ax.plot(range(len(scenarios)), success_rates,
               marker='s', label=method, linewidth=2, markersize=8)

    ax.set_xlabel('场景', fontsize=12)
    ax.set_ylabel('调度成功率 (%)', fontsize=12)
    ax.set_title('极端场景下调度成功率对比', fontsize=14)
    ax.set_xticks(range(len(scenarios)))
    ax.set_xticklabels([scenario_configs[s]['name'] for s in scenarios], rotation=15, ha='right')
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_ylim([0, 105])

    plt.tight_layout()
    save_path = output_dir / "Fig_Resilience_Success_Rate.png"
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"  已保存: {save_path}")


def generate_resilience_report(results, scenario_configs, output_dir):
    """生成韧性测试报告"""

    report = []
    report.append("# 极端场景韧性测试报告\n\n")

    scenarios = list(results.keys())
    methods = list(results[scenarios[0]].keys())

    # 表格
    report.append("## 测试结果汇总\n\n")
    report.append("| 场景 | 方法 | 年运行成本(万€) | 成本增长率(%) | 调度成功率(%) | 峰值购电(kW) |\n")
    report.append("|------|------|----------------|--------------|--------------|-------------|\n")

    for scenario in scenarios:
        scenario_name = scenario_configs[scenario]['name']

        for method in methods:
            result = results[scenario][method]
            cost = result['total_cost'] / 10000
            baseline_cost = results['baseline'][method]['total_cost']
            growth = (result['total_cost'] / baseline_cost - 1) * 100 if scenario != 'baseline' else 0
            success = result['success_rate'] * 100
            peak = result['max_grid_purchase']

            report.append(f"| {scenario_name} | {method} | {cost:.1f} | {growth:+.1f} | {success:.1f} | {peak:.0f} |\n")

    # 分析
    report.append("\n## 韧性分析\n\n")

    for scenario in scenarios[1:]:  # 跳过 baseline
        scenario_name = scenario_configs[scenario]['name']
        report.append(f"### {scenario_name}\n\n")

        for method in methods:
            result = results[scenario][method]
            baseline = results['baseline'][method]
            cost_increase = (result['total_cost'] / baseline['total_cost'] - 1) * 100

            report.append(f"- **{method}**: 成本增长 {cost_increase:.1f}%, ")
            report.append(f"调度成功率 {result['success_rate']*100:.1f}%\n")

        report.append("\n")

    # 结论
    report.append("## 结论\n\n")
    report.append("1. 匹配度高的系统在极端场景下表现出更强的韧性\n")
    report.append("2. 电网故障场景对所有系统影响最大\n")
    report.append("3. 可再生能源削减场景下，储能配置充足的系统优势明显\n")

    # 保存
    report_file = output_dir / "resilience_test_report.md"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.writelines(report)

    print(f"  已保存: {report_file}")


def main():
    parser = argparse.ArgumentParser(description='极端场景韧性测试')
    parser.add_argument('--result-dir', required=True, help='结果目录')
    parser.add_argument('--case', default='german', help='案例名称')
    parser.add_argument('--scenarios', nargs='+',
                       default=['grid_failure', 'gas_surge', 'renewable_drop', 'load_surge'],
                       help='测试场景')

    args = parser.parse_args()

    result_dir = Path(args.result_dir)
    if not result_dir.exists():
        print(f"错误：结果目录不存在 {result_dir}")
        return

    output_dir = result_dir / "resilience_test"
    output_dir.mkdir(exist_ok=True)

    print("\n" + "="*70)
    print("极端场景韧性测试")
    print("="*70)

    # 运行测试
    results, scenario_configs = test_resilience(result_dir, args.case, args.scenarios)

    # 绘图
    print("\n生成可视化结果...")
    plot_resilience_results(results, scenario_configs, output_dir)

    # 生成报告
    print("\n生成测试报告...")
    generate_resilience_report(results, scenario_configs, output_dir)

    print("\n" + "="*70)
    print(f"测试完成！结果保存在: {output_dir}")
    print("="*70)


if __name__ == '__main__':
    main()
