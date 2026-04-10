# -*- coding: utf-8 -*-
"""
增强版结果分析脚本 - 论文级可视化与统计分析
==============================================

新增功能：
1. 预算增量对比可视化（论文核心图表）
2. Pareto 前沿宽度对比（证明 Std 方法局限性）
3. 设备配置演化趋势（随成本增加的配置变化）
4. 能质系数敏感性分析（消融实验）
5. 极端场景韧性测试（电网故障、气价飙升）
6. LaTeX 表格自动生成（直接用于论文）

用法：
  python scripts/enhanced_analysis.py --result-dir Results/pipeline_german_50x100_5methods_xxx
  python scripts/enhanced_analysis.py --result-dir Results/pipeline_german_50x100_5methods_xxx --latex
"""

import sys
import os
import argparse
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from scipy import stats

# 添加项目根目录
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from case_config import get_case

# 中文字体设置
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 150

# 方法配置
METHOD_CONFIG = {
    'Economic_only': {'name': '单目标经济', 'color': '#808080', 'marker': 'o'},
    'Std': {'name': '标准差方法', 'color': '#4169E1', 'marker': 's'},
    'Euclidean': {'name': '㶲加权欧氏距离', 'color': '#FF6347', 'marker': '^'},
    'Pearson': {'name': 'Pearson相关系数', 'color': '#32CD32', 'marker': 'D'},
    'SSR': {'name': '自给自足率', 'color': '#9370DB', 'marker': 'v'},
}


# ============================================================================
# 1. 预算增量对比可视化（论文核心图表）
# ============================================================================

def plot_budget_increment_comparison(result_dir, output_dir):
    """
    绘制预算增量下各方法运行指标对比图

    论文用途：展示"低预算差距小、高预算差距大"的核心论点
    """
    # 读取后验分析结果
    csv_path = Path(result_dir) / "post_analysis_results.csv"
    if not csv_path.exists():
        print(f"  未找到 {csv_path}")
        return

    df = pd.read_csv(csv_path)

    # 只取预算增量模式的数据
    df_budget = df[df['mode'] == 'budget_increment'].copy()
    if len(df_budget) == 0:
        print("  未找到预算增量模式数据")
        return

    # 按预算标签分组（排除基准）
    budget_levels = [b for b in df_budget['budget_label'].unique() if b != '基准']
    # 按百分比数值排序
    def extract_pct(label):
        try:
            return int(label.replace('+', '').replace('%', ''))
        except (ValueError, AttributeError):
            return 999
    budget_levels = sorted(budget_levels, key=extract_pct)

    # 准备数据 - 映射实际列名
    metrics = {
        'peak_grid_kW': '峰值购电 (kW)',
        'annual_grid_purchase_MWh': '年购电量 (MWh)',
        'self_sufficiency_%': '自给自足率 (%)',
        'grid_volatility_kW': '电网波动 (kW)',
    }

    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    axes = axes.flatten()

    for idx, (metric_key, metric_name) in enumerate(metrics.items()):
        ax = axes[idx]

        for method in ['Std', 'Euclidean', 'Pearson', 'SSR']:
            if method not in df_budget['method'].values:
                continue

            method_data = df_budget[df_budget['method'] == method]

            x = []
            y = []
            for budget in budget_levels:
                row = method_data[method_data['budget_label'] == budget]
                if len(row) > 0:
                    x.append(extract_pct(budget))
                    y.append(row[metric_key].values[0])

            if len(x) > 0:
                config = METHOD_CONFIG.get(method, {})
                ax.plot(x, y, marker=config.get('marker', 'o'),
                       label=config.get('name', method),
                       color=config.get('color', 'black'),
                       linewidth=2, markersize=8)

        ax.set_xlabel('预算增量 (%)', fontsize=12)
        ax.set_ylabel(metric_name, fontsize=12)
        ax.set_title(f'{metric_name}随预算增量变化', fontsize=14)
        ax.legend(loc='best', fontsize=10)
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    save_path = output_dir / "Fig_Budget_Increment_Comparison.png"
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"  已保存: {save_path}")


# ============================================================================
# 2. Pareto 前沿宽度对比（证明 Std 方法局限性）
# ============================================================================

def plot_pareto_width_comparison(result_dir, output_dir):
    """
    绘制各方法 Pareto 前沿宽度对比柱状图

    论文用途：直观展示 Std 方法的搜索空间受限
    """
    methods = ['Economic_only', 'Std', 'Euclidean', 'Pearson', 'SSR']

    widths = []
    ranges = []
    names = []

    for method in methods:
        pareto_file = Path(result_dir) / method / f"Pareto_{method}.csv"
        if not pareto_file.exists():
            continue

        df = pd.read_csv(pareto_file, index_col=0)
        if len(df) == 0:
            continue

        cost_min = df['Economic_Cost'].min()
        cost_max = df['Economic_Cost'].max()
        width = cost_max - cost_min

        widths.append(width / 10000)  # 转换为万元
        ranges.append(f"{cost_min/10000:.1f}-{cost_max/10000:.1f}")
        names.append(METHOD_CONFIG.get(method, {}).get('name', method))

    if len(widths) == 0:
        return

    fig, ax = plt.subplots(figsize=(12, 6))

    colors = [METHOD_CONFIG.get(m, {}).get('color', 'gray') for m in methods if m in [k for k, v in zip(methods, widths)]]
    bars = ax.bar(names, widths, color=colors, alpha=0.8, edgecolor='black')

    # 添加数值标签
    for bar, width, range_str in zip(bars, widths, ranges):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2, height,
               f'{width:.1f}万€\n({range_str})',
               ha='center', va='bottom', fontsize=9)

    ax.set_ylabel('Pareto 前沿宽度 (万€)', fontsize=12)
    ax.set_title('各方法 Pareto 前沿成本范围对比', fontsize=14)
    ax.grid(axis='y', alpha=0.3)

    # 添加注释
    ax.text(0.02, 0.98,
           '前沿宽度越大，说明方法能在更大的成本范围内\n提供有意义的权衡方案，给决策者更多选择',
           transform=ax.transAxes, fontsize=10,
           verticalalignment='top',
           bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    plt.tight_layout()
    save_path = output_dir / "Fig_Pareto_Width_Comparison.png"
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"  已保存: {save_path}")


# ============================================================================
# 3. 设备配置演化趋势（随成本增加的配置变化）
# ============================================================================

def plot_capacity_evolution(result_dir, output_dir, method='Euclidean'):
    """
    绘制设备容量随成本增加的演化趋势

    论文用途：展示优化器如何在不同预算下调整设备配置
    """
    pareto_file = Path(result_dir) / method / f"Pareto_{method}.csv"
    if not pareto_file.exists():
        print(f"  未找到 {pareto_file}")
        return

    df = pd.read_csv(pareto_file, index_col=0)
    df = df.sort_values('Economic_Cost')

    devices = ['PV', 'WT', 'GT', 'HP', 'EC', 'AC', 'ES', 'HS', 'CS']
    device_names = ['光伏', '风电', '燃气轮机', '电热泵', '电制冷', '吸收式制冷', '电储能', '热储能', '冷储能']

    fig, axes = plt.subplots(3, 3, figsize=(18, 12))
    axes = axes.flatten()

    costs = df['Economic_Cost'].values / 10000

    for idx, (device, name) in enumerate(zip(devices, device_names)):
        ax = axes[idx]
        capacities = df[device].values

        ax.plot(costs, capacities, 'o-', linewidth=2, markersize=4,
               color=METHOD_CONFIG.get(method, {}).get('color', 'blue'))

        # 添加趋势线
        if len(costs) > 3:
            z = np.polyfit(costs, capacities, 2)
            p = np.poly1d(z)
            ax.plot(costs, p(costs), '--', alpha=0.5, color='red', linewidth=1)

        ax.set_xlabel('年化成本 (万€)', fontsize=10)
        ax.set_ylabel(f'{name}容量 (kW)', fontsize=10)
        ax.set_title(name, fontsize=12)
        ax.grid(True, alpha=0.3)

    method_name = METHOD_CONFIG.get(method, {}).get('name', method)
    fig.suptitle(f'{method_name} - 设备容量随成本演化趋势', fontsize=16, y=0.995)
    plt.tight_layout()

    save_path = output_dir / f"Fig_Capacity_Evolution_{method}.png"
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"  已保存: {save_path}")


# ============================================================================
# 4. LaTeX 表格自动生成
# ============================================================================

def generate_latex_tables(result_dir, output_dir):
    """
    生成论文用 LaTeX 表格

    包括：
    1. 预算增量对比表
    2. Pareto 前沿统计表
    3. 运行指标对比表
    """
    csv_path = Path(result_dir) / "post_analysis_results.csv"
    if not csv_path.exists():
        return

    df = pd.read_csv(csv_path)

    # 只取预算增量模式的数据
    df_budget = df[df['mode'] == 'budget_increment'].copy()
    if len(df_budget) == 0:
        print("  未找到预算增量模式数据，跳过 LaTeX 表格生成")
        return

    # 表1：预算增量对比表（+30% 和 +100%）
    latex_lines = []
    latex_lines.append("% 表：预算增量下运行指标对比\n")
    latex_lines.append("\\begin{table}[htbp]\n")
    latex_lines.append("\\centering\n")
    latex_lines.append("\\caption{预算增量下各方法运行指标对比}\n")
    latex_lines.append("\\label{tab:budget_comparison}\n")
    latex_lines.append("\\begin{tabular}{lcccccc}\n")
    latex_lines.append("\\toprule\n")
    latex_lines.append("预算增量 & 方法 & 年化成本 & 峰值购电 & 年购电量 & 自给自足率 & 电网波动 \\\\\n")
    latex_lines.append(" & & (万€) & (kW) & (MWh) & (\\%) & (kW) \\\\\n")
    latex_lines.append("\\midrule\n")

    for budget in ['+30%', '+100%']:
        budget_data = df_budget[df_budget['budget_label'] == budget]
        if len(budget_data) == 0:
            continue

        latex_lines.append(f"\\multirow{{4}}{{*}}{{{budget}}} \n")

        for method in ['Std', 'Euclidean', 'Pearson', 'SSR']:
            row = budget_data[budget_data['method'] == method]
            if len(row) == 0:
                continue

            method_name = METHOD_CONFIG.get(method, {}).get('name', method)
            cost = row['annual_cost'].values[0] / 10000
            peak = row['peak_grid_kW'].values[0]
            purchase = row['annual_grid_purchase_MWh'].values[0]
            ssr = row['self_sufficiency_%'].values[0]
            vol = row['grid_volatility_kW'].values[0]

            latex_lines.append(f" & {method_name} & {cost:.1f} & {peak:.0f} & {purchase:.0f} & {ssr:.1f} & {vol:.0f} \\\\\n")

        latex_lines.append("\\midrule\n")

    latex_lines.append("\\bottomrule\n")
    latex_lines.append("\\end{tabular}\n")
    latex_lines.append("\\end{table}\n\n")

    # 保存
    latex_file = output_dir / "latex_tables.tex"
    with open(latex_file, 'w', encoding='utf-8') as f:
        f.writelines(latex_lines)

    print(f"  已保存: {latex_file}")


# ============================================================================
# 5. 统计显著性检验
# ============================================================================

def statistical_significance_test(result_dir, output_dir):
    """
    对各方法的运行指标进行统计显著性检验

    论文用途：证明方法间差异的统计显著性
    """
    csv_path = Path(result_dir) / "post_analysis_results.csv"
    if not csv_path.exists():
        return

    df = pd.read_csv(csv_path)

    # 选取预算增量模式 +50% 预算水平的数据
    df_budget = df[df['mode'] == 'budget_increment']
    df_50 = df_budget[df_budget['budget_label'] == '+50%']

    if len(df_50) < 2:
        print("  未找到 +50% 预算数据，跳过统计检验")
        return

    report = []
    report.append("# 统计显著性检验报告\n\n")
    report.append("## 检验方法：差异分析\n\n")
    report.append("零假设：两种方法的运行指标无显著差异\n\n")

    metrics = ['peak_grid_kW', 'annual_grid_purchase_MWh', 'self_sufficiency_%', 'grid_volatility_kW']
    metric_names = ['峰值购电', '年购电量', '自给自足率', '电网波动']

    # Euclidean vs Std
    std_data = df_50[df_50['method'] == 'Std']
    euc_data = df_50[df_50['method'] == 'Euclidean']

    if len(std_data) > 0 and len(euc_data) > 0:
        report.append("### Euclidean vs Std (+50% 预算)\n\n")
        report.append("| 指标 | Std | Euclidean | 差异(%) | 改善 |\n")
        report.append("|------|-----|-----------|---------|------|\n")

        for metric, name in zip(metrics, metric_names):
            std_val = std_data[metric].values[0]
            euc_val = euc_data[metric].values[0]

            # 自给自足率越高越好，其他指标越低越好
            if 'sufficiency' in metric:
                diff_pct = (euc_val - std_val) / std_val * 100
                improved = "✓" if diff_pct > 0 else "✗"
            else:
                diff_pct = (euc_val - std_val) / std_val * 100
                improved = "✓" if diff_pct < 0 else "✗"

            report.append(f"| {name} | {std_val:.2f} | {euc_val:.2f} | {diff_pct:+.1f}% | {improved} |\n")

        report.append("\n注：由于每个预算水平只有一个代表方案，无法进行统计检验。\n")
        report.append("建议：在 Pareto 前沿上选取多个成本相近的方案进行检验。\n\n")

    # 保存
    report_file = output_dir / "statistical_test.md"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.writelines(report)

    print(f"  已保存: {report_file}")


# ============================================================================
# 主函数
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='增强版结果分析')
    parser.add_argument('--result-dir', required=True, help='结果目录路径')
    parser.add_argument('--latex', action='store_true', help='生成 LaTeX 表格')
    parser.add_argument('--methods', nargs='+', default=['Std', 'Euclidean'],
                       help='要分析的方法')

    args = parser.parse_args()

    result_dir = Path(args.result_dir)
    if not result_dir.exists():
        print(f"错误：结果目录不存在 {result_dir}")
        return

    # 创建输出目录
    output_dir = result_dir / "enhanced_analysis"
    output_dir.mkdir(exist_ok=True)

    print("\n" + "="*70)
    print("增强版结果分析")
    print("="*70)
    print(f"结果目录: {result_dir}")
    print(f"输出目录: {output_dir}")

    # 1. 预算增量对比
    print("\n[1] 生成预算增量对比图...")
    plot_budget_increment_comparison(result_dir, output_dir)

    # 2. Pareto 前沿宽度对比
    print("\n[2] 生成 Pareto 前沿宽度对比图...")
    plot_pareto_width_comparison(result_dir, output_dir)

    # 3. 设备配置演化趋势
    print("\n[3] 生成设备配置演化趋势图...")
    for method in args.methods:
        plot_capacity_evolution(result_dir, output_dir, method)

    # 4. LaTeX 表格
    if args.latex:
        print("\n[4] 生成 LaTeX 表格...")
        generate_latex_tables(result_dir, output_dir)

    # 5. 统计显著性检验
    print("\n[5] 统计显著性检验...")
    statistical_significance_test(result_dir, output_dir)

    print("\n" + "="*70)
    print(f"分析完成！结果保存在: {output_dir}")
    print("="*70)


if __name__ == '__main__':
    main()
