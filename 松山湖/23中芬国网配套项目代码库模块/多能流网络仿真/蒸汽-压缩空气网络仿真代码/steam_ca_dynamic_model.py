# -*- coding: utf-8 -*-
"""
蒸汽管网
拓扑结构计算，加入了每个点的延时时间计算
confirmed
"""

__author__ = 'Shuting Zhang'

import time
import numpy as np
import pandas as pd
import xlsxwriter
import math
from cmath import phase
from scipy.fftpack import fft
from matplotlib import pyplot as plt
from contextlib import contextmanager
from sko.GA import GA

@contextmanager
def context(event):
    t0 = time.time()
    print('[{}] {} starts ...'.format(time.strftime('%Y-%m-%d %H:%M:%S'), event))
    yield
    print('[{}] {} ends ...'.format(time.strftime('%Y-%m-%d %H:%M:%S'), event))
    print('[{}] {} runs for {:.2f} s'.format(time.strftime('%Y-%m-%d %H:%M:%S'), event, time.time() - t0))

#定义计算截断频率的函数
def NumberFreqCal(TSData: 'time series data', trunc_ratio: float = 5e-3) -> int:
    # 判断要用几个频率。 当某个频率下的幅值不到直流分量的trunc_ratio时，停止。
    # TSData是没有所谓维度信息的numpy array
    numberFreq_required = 0
    # conjugate treatment。共轭部分是对称的，先判断，在前一半的samples里面，到底第几编号的频率开始，他的幅值就不到0频率的trunc_ratio了。之后就用那里的。
    FD_1stHalf = np.split(fft(TSData), 2)[0]  # 分为两部分，取第一部分。
    Invalid_freq_inx = np.flatnonzero(abs(FD_1stHalf) / np.max(abs(FD_1stHalf)) < trunc_ratio)
    Trun_freq_inx = np.min(Invalid_freq_inx)
    numberFreq_required = Trun_freq_inx
    # 注意，这里其实减了1.比如说，如果第6号频率（0,1,2,3,4,5,6）的amplitude，小于截断频率了，那么我就总共用6个频率（0,1,2,3,4,5）
    numberFreqUsed = int(numberFreq_required)
    return numberFreqUsed

with context('数据输入、读取与处理'):
    # 原始数据
    pipe_table = pd.read_excel('../data/BinHai_steam_network_topology.xls', sheet_name='Branch')
    node_table = pd.read_excel('../data/BinHai_steam_network_topology.xls', sheet_name='Node')
    load_table = pd.read_excel('../data/BinHai_steam_network_topology.xls', sheet_name='Load')
    pres_table = pd.read_excel('../data/BinHai_steam_network_topology.xls', sheet_name='Pressure')
    # 数据初步处理
    numpipe = len(pipe_table)  # 支路数
    numnode = len(node_table)  # 节点数
    l = pipe_table['长度(km)'].values * 1e3  # 长度，m
    d = pipe_table['管径(mm)'].values / 1e3  # 管径，m
    lam = pipe_table['粗糙度'].values  # 摩擦系数
    cp = pipe_table['压气机(MPa)'].values * 1e6  # 支路增压，Pa
    T = 277+273.15#加权平均
    R = -0.0088*T**2+10.835*T-2863.9#低压、中压、高压蒸汽有各自的物性表达式
    Apipe = np.pi * d ** 2 / 4  # 管道截面积
    # 节点分类
    fix_G = node_table[node_table['节点类型'] == '定注入'].index.values
    fix_p = node_table[node_table['节点类型'] == '定压力'].index.values
    fix_p = np.append(fix_p, numnode)  # 最后一个节点，大地节点，是定压力节点
    # 节点-支路关联矩阵
    A = np.zeros([numnode, numpipe])
    A0 = np.zeros([numnode + 1, numpipe * 3])  # 最后一行是地节点
    Ap = np.zeros([numnode, numpipe])
    Ap0 = np.zeros([numnode + 1, numpipe * 3])  # 最后一行是地节点
    for row in pipe_table.iterrows():
        A[int(row[1][1]) - 1, row[0]] = 1
        A[int(row[1][2]) - 1, row[0]] = -1
        A0[int(row[1][1]) - 1, row[0] * 3] = 1
        A0[int(row[1][2]) - 1, row[0] * 3] = -1
        A0[int(row[1][1]) - 1, row[0] * 3 + 1] = 1
        A0[-1, row[0] * 3 + 1] = -1
        A0[int(row[1][2]) - 1, row[0] * 3 + 2] = 1
        A0[-1, row[0] * 3 + 2] = -1
        Ap[int(row[1][1]) - 1, row[0]] = 1
        Ap[int(row[1][2]) - 1, row[0]] = 0
        Ap0[int(row[1][1]) - 1, row[0] * 3] = 1
        Ap0[int(row[1][2]) - 1, row[0] * 3] = 0
        Ap0[int(row[1][1]) - 1, row[0] * 3 + 1] = 1
        Ap0[-1, row[0] * 3 + 1] = 0
        Ap0[int(row[1][2]) - 1, row[0] * 3 + 2] = 1
        Ap0[-1, row[0] * 3 + 2] = 0

with context('动态潮流计算'):
    #参数设置
    set_v = 20.0#速度基值，根据工况确定，单位是m/s
    interpolation = 6  # interpolation倍插值，原数据间隔/interpolation s一个点，最终输出的结果的间隔
    trun_ratio = 1e-4#截断频率允许误差
    NumerFreq_default = 150#默认的要选取的频率个数
    inter_time_origin = 60
    inter_time_expect = inter_time_origin/interpolation
    sim_time_span = int(load_table.shape[0]*(inter_time_origin/60)/60)#实际仿真的时长，由原始数据总长度决定
    k = 1 / 6  # 12*k = 要叠加的历史边界条件长度，小时

    v = np.array([set_v] * numpipe)  # 流速基值，平启动
    for itera in range(numpipe):
        # 确定时域分布参数
        Rg = [lam[i] * v[i] / Apipe[i] / d[i] for i in range(numpipe)]
        Lg = [1 / Apipe[i] for i in range(numpipe)]
        Cg = [Apipe[i] / (R * T) for i in range(numpipe)]
        Ug = [-lam[i] * v[i] ** 2 / 2 / (R * T) / d[i] for i in range(numpipe)]

        Node_Injection = load_table.fillna(0).values   # kg/s,原数据为正值的t/h
        Node_Pressure = pres_table.fillna(0).values * 1e6  # Pa

        # TD_E: Time Domain Encourage (节点数行*时间点数列)
        TD_E_G = []
        TD_E_p = []
        for row in node_table.iterrows():
            TD_E_G.append(Node_Injection[:, row[0]])
            TD_E_p.append(Node_Pressure[:, row[0]])
        # 增加地节点
        TD_E_G.append(np.zeros(TD_E_G[-1].shape))
        TD_E_p.append(np.zeros(TD_E_p[-1].shape))
        TD_E_G = np.array(TD_E_G)
        TD_E_p = np.array(TD_E_p)

        # 原始时域激励数据，5min一个点，144个点，共12小时
        TD_E_G = TD_E_G.repeat(interpolation, axis=1)
        TD_E_p2 = np.zeros([numnode + 1, 360 * sim_time_span])
        for i in range(numnode + 1):
            TD_E_p2[i, :] = np.interp(np.linspace(inter_time_expect, int(3600 * sim_time_span), int(3600 / inter_time_expect * sim_time_span)),  # 插成10s一个点
                                      np.linspace(inter_time_origin, int(3600 * sim_time_span), int(3600 / inter_time_origin * sim_time_span)),  # 原来300s一个点
                                      TD_E_p[i, :])
            # TD_E_p2[i, :] = np.interp(np.linspace(10, 3600 * 12, 360 * 12),  # 插成10s一个点
            #                           np.linspace(300, 3600 * 12, 12 * 12),  # 原来300s一个点
            #                           TD_E_p[i, :])
        TD_E_p = TD_E_p2

        # 在0时刻之前叠加一段稳态激励，边值转初值
        initialization = int(TD_E_G.shape[1] * k)  # 插值
        TD_E_G = np.concatenate((TD_E_G[:, 0].reshape([-1, 1]).repeat(initialization, axis=1), TD_E_G), axis=1)
        TD_E_p = np.concatenate((TD_E_p[:, 0].reshape([-1, 1]).repeat(initialization, axis=1), TD_E_p), axis=1)
        TD_GL = np.zeros([numpipe, TD_E_G.shape[1]])  # 线路流量

        # #输出插值后的原始数据
        # Tp_te = []
        # Tp_te = TD_E_p
        # Tg_te = []
        # Tg_te = TD_E_G
        #
        # # 输出插值后的原始数据
        # writer = pd.ExcelWriter('te_inter_p.xlsx', engine='openpyxl')
        # Tp_te = pd.DataFrame(Tp_te)
        # Tp_te.to_excel(excel_writer=writer)
        # writer.close()
        # writer = pd.ExcelWriter('te_inter_g.xlsx', engine='openpyxl')
        # Tg_te = pd.DataFrame(Tg_te)
        # Tg_te.to_excel(excel_writer=writer)
        # writer.close()

        # 计算截断频率
        NumFreqp_max = 0
        NumFreqG_max = 0
        nt = TD_E_G.shape[1]  # 时域总长度
        for row in node_table.iterrows():
            if row[1]['节点类型'] == '定压力':
                Numpf = TD_E_p[row[0], :]
                if Numpf[0] != 0:#不是零的输入才能进行截断频率和傅里叶变换计算。这里可以对多个用户输入流量变化进行计算，取较大值
                    NumerFreqp = NumberFreqCal(Numpf, trun_ratio)
                    if NumerFreqp > NumFreqp_max:
                        NumFreqp_max = NumerFreqp
            elif row[1]['节点类型'] == '定注入':
                NumGf = TD_E_G[row[0], :]
                if NumGf[0] != 0:
                    NumerFreqG = NumberFreqCal(NumGf, trun_ratio)
                    if NumerFreqG > NumFreqG_max:
                        NumFreqG_max = NumerFreqG
            else:
                assert 0
        trun_freq = np.max([NumFreqG_max, NumFreqp_max, NumerFreq_default])

        # FD_E: Frequency Domain Encourage (节点数行*频域分量数列)
        FD_E_G = []
        FD_E_p = []
        nf = trun_freq * 2  # 保留的频率分量数
        fr = 1 / (12 * 3600 * (k + 1))  # 频率分辨率（frequency resolution）
        FD_GL = np.zeros([numpipe, nf], dtype='complex_')
        FD_GL_FROM = np.zeros([numpipe, nf], dtype='complex_')
        FD_GL_TO = np.zeros([numpipe, nf], dtype='complex_')
        for row in node_table.iterrows():
            if row[1]['节点类型'] == '定压力':
                Gf = np.zeros(nf, dtype='complex_')
                pf = (fft(TD_E_p[row[0], :]) / nt * 2)[:nf]
                pf[0] /= 2
            elif row[1]['节点类型'] == '定注入':
                pf = np.zeros(nf, dtype='complex_')
                Gf = (fft(TD_E_G[row[0], :]) / nt * 2)[:nf]
                Gf[0] /= 2
            else:
                assert 0
            FD_E_G.append(Gf)
            FD_E_p.append(pf)
        # 增加地节点
        FD_E_G.append(np.zeros(nf, dtype='complex_'))
        FD_E_p.append(np.zeros(nf, dtype='complex_'))
        FD_E_G = np.array(FD_E_G)
        FD_E_p = np.array(FD_E_p)

        # 单频能路计算, 遍历所有频率分量
        for fi in range(FD_E_G.shape[1]):
            f = fi * fr
            # 计算各支路的频域集总参数（pi型等值）
            Yb1, Yb2, Zb, Ub = [], [], [], []
            for i in range(numpipe):
                Z = Rg[i] + complex(0, 1) * 2 * np.pi * f * Lg[i]
                Y = complex(0, 1) * 2 * np.pi * f * Cg[i]
                za = np.cosh(np.sqrt(Ug[i] ** 2 + 4 * Z * Y) / 2 * l[i]) - Ug[i] / np.sqrt(
                    Ug[i] ** 2 + 4 * Z * Y) * np.sinh(np.sqrt(Ug[i] ** 2 + 4 * Z * Y) / 2 * l[i])
                za = za * np.exp(-Ug[i] * l[i] / 2)
                zb = -2 * Z / np.sqrt(Ug[i] ** 2 + 4 * Z * Y) * np.sinh(np.sqrt(Ug[i] ** 2 + 4 * Z * Y) / 2 * l[i])
                zb = zb * np.exp(-Ug[i] * l[i] / 2)
                zc = -2 * Y / np.sqrt(Ug[i] ** 2 + 4 * Z * Y) * np.sinh(np.sqrt(Ug[i] ** 2 + 4 * Z * Y) / 2 * l[i])
                zc = zc * np.exp(-Ug[i] * l[i] / 2)
                zd = np.cosh(np.sqrt(Ug[i] ** 2 + 4 * Z * Y) / 2 * l[i]) + Ug[i] / np.sqrt(
                    Ug[i] ** 2 + 4 * Z * Y) * np.sinh(np.sqrt(Ug[i] ** 2 + 4 * Z * Y) / 2 * l[i])
                zd = zd * np.exp(-Ug[i] * l[i] / 2)
                Yb1.append((za * zd - zb * zc - za) / zb)  # 动态潮流中，接地支路起作用
                Yb2.append((1 - zd) / zb)  # 动态潮流中，接地支路起作用
                Zb.append(-zb)
                Ub.append(1 - za * zd + zb * zc)

            # 形成支路导纳矩阵
            yb = np.diag(np.array([[1 / Zb[i], Yb1[i], Yb2[i]] for i in range(numpipe)]).reshape(-1))
            # 形成支路受控电压源矩阵
            ub = np.diag(np.array([[Ub[i], 0, 0] for i in range(numpipe)]).reshape(-1))
            # 支路气压源向量
            cpexp = np.array([[cp[i], 0, 0] for i in range(len(cp))]).reshape([-1, 1]) if fi == 0 else np.zeros([18, 1])
            # 形成广义节点导纳矩阵
            Yg_ = np.matmul(np.matmul(A0, yb), A0.T) - np.matmul(np.matmul(np.matmul(A0, yb), ub), Ap0.T)
            Yg_11 = Yg_[fix_G][:, fix_G]
            Yg_12 = Yg_[fix_G][:, fix_p]
            Yg_21 = Yg_[fix_p][:, fix_G]
            Yg_22 = Yg_[fix_p][:, fix_p]

            # 求解网络方程
            FD_E_p[fix_G, fi] = np.matmul(np.linalg.inv(Yg_11), (
                        (FD_E_G[fix_G, fi]) - np.matmul(
                    Yg_12, FD_E_p[fix_p, fi])))
            FD_E_G[fix_p, fi] = np.matmul(Yg_21, FD_E_p[fix_G, fi]) + np.matmul(Yg_22, FD_E_p[fix_p, fi])

            # 节点状态变量转支路状态变量
            FD_GL[:, fi] = (np.matmul(A.T, FD_E_p[:-1, fi]).reshape(-1) - (
                        np.array(Ub).reshape([-1]) * np.matmul(Ap.T, FD_E_p[:-1, fi]) - (
                    cp if fi == 0 else np.zeros(numpipe))).reshape(-1)) / np.array(Zb)

            Afrom, Ato = A.copy(), A.copy()
            Afrom[Afrom < 0] = 0
            Ato[Ato > 0] = 0
            # 首端流量
            FD_GL_FROM[:, fi] = (np.matmul(A.T, FD_E_p[:-1, fi]).reshape(-1) - (
                        np.array(Ub).reshape([-1]) * np.matmul(Ap.T, FD_E_p[:-1, fi]) - (
                    cp if fi == 0 else np.zeros(numpipe))).reshape(-1)) / np.array(Zb) + np.matmul(Afrom.T, FD_E_p[:-1,
                                                                                                            fi].reshape(
                [-1, 1])).reshape(-1) * np.array(Yb1)
            # 末端流量
            FD_GL_TO[:, fi] = (np.matmul(A.T, FD_E_p[:-1, fi]).reshape(-1) - (
                        np.array(Ub).reshape([-1]) * np.matmul(Ap.T, FD_E_p[:-1, fi]) - (
                    cp if fi == 0 else np.zeros(numpipe))).reshape(-1)) / np.array(Zb) + np.matmul(Ato.T, FD_E_p[:-1,
                                                                                                          fi].reshape(
                [-1, 1])).reshape(-1) * np.array(Yb2)

        # from FD_E to TD_E
        ts = np.linspace(10, nt * 10, nt)
        # 定压力节点的注入
        for fi in range(nf):
            for node in fix_p:
                TD_E_G[node, :] += abs(FD_E_G[node, fi]) * np.cos(2 * np.pi * fi * fr * ts + phase(FD_E_G[node, fi]))
        # 定注入节点的压力
        for fi in range(nf):
            for node in fix_G:
                TD_E_p[node, :] += abs(FD_E_p[node, fi]) * np.cos(2 * np.pi * fi * fr * ts + phase(FD_E_p[node, fi]))
        # 支路流量
        TD_GL_FROM = np.zeros(TD_GL.shape)
        TD_GL_TO = np.zeros(TD_GL.shape)
        for fi in range(nf):
            for branch in range(numpipe):
                TD_GL[branch, :] += abs(FD_GL[branch, fi]) * np.cos(2 * np.pi * fi * fr * ts + phase(FD_GL[branch, fi]))
                TD_GL_FROM[branch, :] += abs(FD_GL_FROM[branch, fi]) * np.cos(
                    2 * np.pi * fi * fr * ts + phase(FD_GL_FROM[branch, fi]))
                TD_GL_TO[branch, :] += abs(FD_GL_TO[branch, fi]) * np.cos(
                    2 * np.pi * fi * fr * ts + phase(FD_GL_TO[branch, fi]))
        # 支路流速
        TD_v = TD_GL / np.matmul(Ap.T, TD_E_p[:-1, :]) / Apipe.reshape([-1, 1]) * (R * T)
        # 修正基值
        print('第%d次迭代，失配误差为%.5f' % (itera + 1, np.linalg.norm(v - np.average(abs(TD_v), axis=1))))
        if np.linalg.norm(v - np.average(abs(TD_v), axis=1)) < 1e-1:
            break
        v += (np.average(abs(TD_v), axis=1) - v) * 0.6
with context('延迟时间计算'):
    vv_dt = 0
    if vv_dt == 1:
        #延迟时间计算，管道流量写入节点流量。节点对应管道，需要更改输入表格中delay_branch的节点间的关系
        delay_branch_table = pd.read_excel('./topo_滨海.xls', sheet_name='delay_branch')
        ifc_delay = delay_branch_table['是否为主干道']
        rows, cols = TD_GL.shape
        t_delay = np.zeros((rows, cols))
        GL_node = np.zeros((rows+1, cols))
        delay_numnode = len(GL_node)-1
        A_B = np.zeros([numnode+1, numpipe+1])
        for row in delay_branch_table.iterrows():
            A_B[int(row[1][1]) - 1, row[0]] = 1
        A_B[:, row[0]] = 0
        for i in range(rows+1):
            for j in range(cols):
                if i==6:
                    GL_node[i, j] = TD_GL[i-1, j]
                else:
                    GL_node[i, j] = TD_GL[i, j]
        #先计算主干道延迟
        for i in range(rows):
            for j in range(cols):
                if GL_node[i, j]==0:
                    continue
                else:
                    t_delay[i, j] = math.pi * (d[i] ** 2) * l[i] / 4 / abs(GL_node[i, j])
                    for ks in range(delay_numnode):
                         t_delay[i, j] = t_delay[i, j] + t_delay[ks, j]*A_B[ks, i]
        #再计算支路延迟
        for i in range(rows):
            for j in range(cols):
                if GL_node[i, j]==0:
                    continue
                else:
                    if ifc_delay[i]==2:
                        for ks in range(delay_numnode):
                            t_delay[i, j] = math.pi*(d[i]**2)*l[i] / 4 / abs(GL_node[i, j]) + t_delay[ks, j]* A_B[i, ks]
        #写入excel表格
        workbook = xlsxwriter.Workbook('delaytime.xlsx')
        worksheet = workbook.add_worksheet('delaytime')
        headings = ['时间','1','2','3','4','5','6']
        worksheet.write_row('A1',headings)
        lt=len(t_delay)
        for item in range(lt):
            worksheet.write_column(1,item+1, t_delay[item, :])
        workbook.close()

with context('可视化与输出'):
    vis = 0
    if vis==1:
        TD_E_G *= -1  # 从kg/s转换回kg/s
        TD_E_p /= 1e6  # 从Pa转换回MPa
        plt.figure(1)
        #plt.plot(TD_E_G.T)
        plt.plot(-TD_E_G.T[:, 0], label='1', color='g')
        plt.plot(TD_E_G.T[:, 3], label='4', color='b')
        plt.plot(TD_E_G.T[:, 4], label='5', color='k')
        plt.plot(TD_E_G.T[:, 6], label='7', color='m')
        plt.plot(TD_E_G.T[:, 10], label='11', color='c')
        plt.plot(TD_E_G.T[:, 12], label='13', color='y')
        plt.plot(TD_E_G.T[:, 14], label='15', color='r')
        plt.plot(TD_E_G.T[:, 17], label='18', color='pink')
        plt.plot(TD_E_G.T[:, 19], label='20', color='gold')
        plt.plot(TD_E_G.T[:, 21], label='22', color='peru')
        plt.plot(TD_E_G.T[:, 23], label='24', color='lightcoral')
        plt.plot(TD_E_G.T[:, 24], label='25', color='yellow')
        plt.show()
        plt.figure(2)
        #plt.plot(TD_E_p[:-1].T)
        plt.plot(TD_E_p.T[:, 0], label='1', color='g')
        plt.plot(TD_E_p.T[:, 3], label='4', color='b')
        plt.plot(TD_E_p.T[:, 4], label='5', color='k')
        plt.plot(TD_E_p.T[:, 6], label='7', color='m')
        plt.plot(TD_E_p.T[:, 10], label='11', color='c')
        plt.plot(TD_E_p.T[:, 12], label='13', color='y')
        plt.plot(TD_E_p.T[:, 14], label='15', color='r')
        plt.plot(TD_E_p.T[:, 17], label='18', color='pink')
        plt.plot(TD_E_p.T[:, 19], label='20', color='gold')
        plt.plot(TD_E_p.T[:, 21], label='22', color='peru')
        plt.plot(TD_E_p.T[:, 23], label='24', color='lightcoral')
        plt.plot(TD_E_p.T[:, 24], label='25', color='yellow')
        plt.show()

with context('输出数据'):

    vv_out = 1
    if vv_out ==1:
        #写入流量
        workbook = xlsxwriter.Workbook('output_G_topo_binhai_scenario4_20251009.xlsx')
        worksheet = workbook.add_worksheet('binhai_G')
        headings = ['时间','1','2','3','4','5','6','7','8','9','10','11','12','13','14','15','16','17','18','19','20','21','22','23','24']
        worksheet.write_row('A1',headings)
        lG=len(TD_E_G)
        for item in range(lG):
            worksheet.write_column(1,item+1, TD_E_G[item, :])
        workbook.close()
        #写入压力
        workbook = xlsxwriter.Workbook('output_p_topo_binhai_scenario4_20251009.xlsx')
        worksheet = workbook.add_worksheet('binhai_p')
        headings = ['时间', '1', '2', '3', '4', '5', '6', '7', '8','9','10','11','12','13','14','15','16','17','18','19','20','21','22','23','24']
        worksheet.write_row('A1', headings)
        lp=len(TD_E_p)
        for item in range(lp):
            worksheet.write_column(1, item+1, TD_E_p[item, :])
        workbook.close()


