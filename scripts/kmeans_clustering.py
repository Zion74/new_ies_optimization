# -*- coding: utf-8 -*-
"""
典型日 K-Medoids 聚类（Python 版，替代 kmeansClustering.m）

输入: mergedData.csv  (8760行 × 6列，逐小时数据)
输出: typicalDayData.xlsx  (14个典型日 → 所代表的天列表)

算法: K-Medoids (PAM)，纯 numpy 实现，无需额外工具箱
聚类特征: 每天 24h × 6 维 = 144 维向量，归一化后做欧氏距离
"""

import numpy as np
import pandas as pd
import os

N_CLUSTERS = 14
RANDOM_SEED = 42


def _build_day_matrix(csv_path: str) -> np.ndarray:
    """把 8760×6 的逐小时数据重塑为 365×144 的日特征矩阵"""
    df = pd.read_csv(csv_path)
    data = df.values.astype(float)          # (8760, 6)
    assert data.shape == (8760, 6), f"期望 (8760,6)，实际 {data.shape}"
    day_matrix = data.reshape(365, 24 * 6)  # (365, 144)
    return day_matrix


def _normalize(X: np.ndarray) -> np.ndarray:
    """按列 min-max 归一化，避免量纲差异影响距离"""
    col_min = X.min(axis=0)
    col_max = X.max(axis=0)
    rng = col_max - col_min
    rng[rng == 0] = 1.0          # 防止除零
    return (X - col_min) / rng


def kmedoids(X: np.ndarray, k: int, max_iter: int = 300, random_state: int = 42) -> tuple:
    """
    PAM K-Medoids 聚类

    Parameters
    ----------
    X : (n, d) 特征矩阵
    k : 簇数
    max_iter : 最大迭代次数
    random_state : 随机种子

    Returns
    -------
    labels      : (n,) 每个样本所属簇的编号 (0-based)
    medoid_idx  : (k,) 每个簇的 medoid 在 X 中的行索引
    """
    rng = np.random.default_rng(random_state)
    n = X.shape[0]

    # 预计算距离矩阵（欧氏距离）
    diff = X[:, None, :] - X[None, :, :]          # (n, n, d)
    dist = np.sqrt((diff ** 2).sum(axis=-1))       # (n, n)

    # 随机初始化 medoids
    medoids = rng.choice(n, size=k, replace=False)

    for _ in range(max_iter):
        # 分配：每个点归入最近 medoid 的簇
        labels = dist[:, medoids].argmin(axis=1)   # (n,)

        new_medoids = medoids.copy()
        for c in range(k):
            members = np.where(labels == c)[0]
            if len(members) == 0:
                continue
            # 簇内总距离最小的点作为新 medoid
            intra = dist[np.ix_(members, members)].sum(axis=1)
            new_medoids[c] = members[intra.argmin()]

        if np.array_equal(np.sort(new_medoids), np.sort(medoids)):
            break
        medoids = new_medoids

    labels = dist[:, medoids].argmin(axis=1)
    return labels, medoids


def run_clustering(
    csv_path: str = "mergedData.csv",
    output_path: str = "typicalDayData.xlsx",
    n_clusters: int = N_CLUSTERS,
    random_state: int = RANDOM_SEED,
) -> pd.DataFrame:
    """
    执行聚类并保存结果

    Returns
    -------
    df : 与原 typicalDayData.xlsx 格式完全一致的 DataFrame
         列: typicalDayId, weight, days
    """
    print(f"读取数据: {csv_path}")
    day_matrix = _build_day_matrix(csv_path)          # (365, 144)
    X_norm = _normalize(day_matrix)

    print(f"执行 K-Medoids 聚类 (k={n_clusters})...")
    labels, medoid_indices = kmedoids(X_norm, k=n_clusters, random_state=random_state)

    # 构建输出表（天编号从 1 开始，与原 MATLAB 版一致）
    rows = []
    for c, med_idx in enumerate(medoid_indices):
        members = np.where(labels == c)[0]          # 0-based 天索引
        typical_day_id = int(med_idx) + 1           # 转为 1-based
        weight = len(members)
        days_str = ",".join(str(d + 1) for d in sorted(members))
        rows.append({
            "typicalDayId": typical_day_id,
            "weight": weight,
            "days": days_str,
        })

    # 按 typicalDayId 排序（与原文件一致）
    df = pd.DataFrame(rows).sort_values("typicalDayId").reset_index(drop=True)

    df.to_excel(output_path, index=False, engine="openpyxl")
    print(f"已保存: {output_path}  ({len(df)} 个典型日，共覆盖 {df['weight'].sum()} 天)")
    return df


if __name__ == "__main__":
    base = os.path.dirname(os.path.abspath(__file__))
    df = run_clustering(
        csv_path=os.path.join(base, "mergedData.csv"),
        output_path=os.path.join(base, "typicalDayData.xlsx"),
    )
    print("\n聚类结果预览:")
    print(df.to_string())
