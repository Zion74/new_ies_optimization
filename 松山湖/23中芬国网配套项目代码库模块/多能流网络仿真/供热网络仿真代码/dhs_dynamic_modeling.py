# -*- coding: utf-8 -*-
"""动态建模核心模块封装

这个 module 就是把动态建模所需要的最核心的函数都封装了起来。
PreSimulationArgsSetup： 计算完整的整体仿真的参数+水力仿真参数
ThermalSimulationArgsCreation： 计算动态热力计算需要用到的 仿真参数 和 输入边界信息
CalWeightedTopoMatrices： 通过节点支路关联矩阵和 pipe 的流量分布，计算出需要的 Ah+ 和 \hat{Ah}
ThermalSimulationBCCreation：这个函数用于给定了excel中的输入边界条件后，将他进行增广，变成可用于Fourier/LaplaceSolver的边界条件，
目前这一函数主要是对FourierSolver起作用，对LaplaceSolver刻意设置为了不起作用。需要注意的是我们给定的输入，时域的而言这是边界条件BC。
转换后，在complex domain 或者 frequency domain就是初始条件IC了。
FourierTransSolver：在给定了所有参数信息后，开展Fourier变换的求解，返回节点温度、管段末端温度、管段首段温度
FourierResultsParser: Fourier变换得到的结果反变换后回时域内，他对时间的因果关系并不敏感，需要把它进行重组使得满足实际情况
LaplaceTransSolver：在给定了所有参数信息后，开展拉普拉斯变换的求解，但是因为这一求解是解析求解，存在局限，他并不返回温度，只返回了结果
CD_Tnodes = M @ CD_Tin + V @ CD_Et 中的 M和V，也许可以用于未来的理论推导来找到最大延迟之类的，或者在CD_Tin、CD_Et显性表达已知的情况下
给出CD_Tnodes的表达式。
LaplaceResultsParser：Laplace变换得到的结果，通过M和V的处理获得了延迟和损耗信息后，需要进行数据变动和补全才能得到合理的结果。
NumberFreqCal： 给定一组时序数据，在设定了截断的幅值比例后，计算需要多少个正频率，由于正负频率是conjugate的，只需要正频率个数就行了。

"""

import numpy as np
import numpy.linalg as linalg
from cmath import phase
from scipy.fft import fft
import pandas as pd
from matplotlib import pyplot as plt
import sympy as sym
import re
from prettytable import PrettyTable


# from uncertainty_quantification.credible_interval_calc import apx_uncertain_interval_vector
# from uncertainty_quantification.moments import moments2cumulants, cumulants2moments
# from scipy.spatial.distance import euclidean, seuclidean, sqeuclidean

def PreSimulationArgsSetup(tabledata: 'tuple of excel sheet',
                           SolverOption: int = 1) -> tuple:
    """
    返回完整的整体仿真参数，其中包含完整的水力仿真参数。
    :param tabledata: 数据导入
    :param SolverOption: 求解器设置
    :return: 整体仿真参数的元组形式和字典形式
    """

    (tb1, tb2, tb3, tb4) = tabledata
    # npipes为热网中管段的个数
    # nnodes为热网中节点的个数
    npipes, nnodes = len(tb2), len(tb1)

    # 直接给出的整体仿真参数
    # 1、数据时长参数（这一部分需要手动设定）
    # steadyTimeBound：稳态缓冲区时间，单位为小时（h）
    # Fourier 求解器使用 steadyTimeBound 参数
    # Laplace 求解器不用 steadyTimeBound 参数 （设置为 0）
    # TODO 未来可以和 laplace solver算出来的 maxdelaytime 对比一下，确认合理的稳态缓冲区时间。
    steadyTimeBound = 0
    # testDataStep：历史数据时间间隔，单位为秒（s）
    # excel | 'Dynamic' sheet | 't/min' column
    # 当前保存数据的 excel 表中的数据读取间隔是 5 分钟一次，历史数据时间间隔设置为 300s。
    testDataStep = 300
    # simulDataStep：仿真时间间隔，单位为秒 （s）
    # 建模过程中，以 10s 一个点作为分辨率，一分钟就有 60/simulDatastep 个点。
    simulDataStep = 10

    # 2、水力热力参数
    MaxHydraulicIter = int(100)  # 水力计算最大迭代次数
    ConvHydraulic = 1e-3  # 水力计算收敛误差
    L = tb2['length'].values * 1e3  # 管道长度，单位 m
    D = tb2['diameter'].values  # 管道直径，单位 m
    lam = tb2['fraction'].values  # 摩擦系数, 无量纲
    rho = 1000  # 物性参数(密度),单位 kg/m^3
    cp = 4200  # 物性参数(定压比热容), 单位 J/(kg*K)
    # 热力参数
    miu = tb2.disspation.values  # 管道散热系数,单位 W/(m*K)
    # 拓扑参数
    # Ah 节点支路关联矩阵，水力
    Ah = np.zeros([nnodes, npipes], dtype=np.int32)
    # 水力、热力共享一个节点支路关联矩阵
    A_thermal = Ah
    # 环境参数，环境温度的设置基于北京市当日的气象数据
    Tamb = 5  # 环境温度,单位 ℃
    # 注意:代码中涉及到的所有温度都是实际温度减去 Tamb.
    # 注意:如果节点输入的温度是实际温度的话,数据处理的时候都要减去 Tamb.

    # 时间空间离散信息
    # 截断频率可以手动给定，也可以自动计算。
    # 手动给定就是给出 numberFreq_want 个频率。注意，这里设定的是所谓的正频率部分的份数，
    # 对后半截（负频率部分），不用考虑，为什么？因为他和正的部分是 conjugate。
    # 这减少了计算的时间，不然理论上你需要计算前后加起来 2*numberFreq_want 个频率分量。
    # 在考虑了共轭的情况下，如果用固定的频率数，用开头的第（numberFreq_want）个频率及其共
    # 轭频率，这个值必须小于 nf_default/2。
    numberFreq_want = 300
    # 如果选择自动给出，那么 numberFreq_want 就不会被用上，随便给定数目。通过设定
    # numberFreqCal 为 True，并给定幅值截断系数。
    CalNumberFreq = True
    # even though CalNumberFreq is given
    # we still wants to calculate whether it is reasonable
    # 幅值小于0.5%的，就砍掉了。如果以后是用功率谱，就要注意，功率谱和幅值谱是不一样的。
    trunc_ratio = 5e-3

    # 间接给出的整体仿真参数
    # 每小时的采样个数
    samplesPerHr = int(3600 / simulDataStep)
    # Fourier 求解器的增广输入数据要用，Laplace求解器不用。
    if SolverOption == 1:
        # 给定历史数据的总小时数
        testDataPeriod = int(len(tb4['t/min']) * testDataStep / 3600)
        # 总仿真时长（最好凑成 24/48h）
        totalSimPeriod = steadyTimeBound + testDataPeriod
    if SolverOption == 2:
        steadyTimeBound = 0
        # 给定历史数据的小时数
        testDataPeriod = int(len(tb4['t/min']) * testDataStep / 3600)
        # 总仿真时长（最好凑成 24/48h）
        totalSimPeriod = steadyTimeBound + testDataPeriod
    for i, row in tb2.iterrows():
        # from node 意思：从节点流出到这个管道，对节点而言这是流出。
        Ah[row['from node'] - 1, i] = 1
        # to node 意思：从管道流入到这个节点，对节点而言这是流入。
        Ah[row['to node'] - 1, i] = -1
    fix_p = np.where(tb1.type1.values == '定压力')[0]  # 定压力的节点编号
    fix_G = np.where(tb1.type1.values == '定注入')[0]  # 定注入的节点编号
    mb = np.ones(npipes) * 5  # 流量基值平启动
    As = np.array([np.pi * d ** 2 / 4 for d in D])  # 管道的横截面积,单位 m^2

    # 时空离散信息的最终版本
    # 每个支路的时序数据个数（例:24 * 360 = 8640）
    nt = int(totalSimPeriod * samplesPerHr)
    # 最小频率间隔
    # 时域的时间为 totalSimPeriod 小时，总时间长度是 totalSimPeriod*3600 秒。
    # 其倒数为最小频率间隔
    fr = 1 / (totalSimPeriod * 3600)
    # 时间跨度(time span)
    ts = np.linspace(simulDataStep, totalSimPeriod * 3600, nt)
    nf_default = nt
    if numberFreq_want > nf_default / 2:
        raise ValueError('numberFreq_want greater than nf_default / 2')

    # 稳态水力计算
    err = []  # 流量失配误差记录
    mbs = [mb.copy()]  # 流量基值的迭代过程记录
    Gb = 0  # 本质上是迭代中的 pipes 流量，注意是一个向量。
    Gn = 0  # 本质上是迭代中的 nodes 流量，注意是一个向量。

    # 返回全局的仿真参数的元组形式和字典形式
    GlobalSimulationArgsTuple = (
        cp, rho, miu, L, As, ts, fr, trunc_ratio, CalNumberFreq,
        numberFreq_want, A_thermal, nnodes, npipes, testDataStep, simulDataStep,
        steadyTimeBound,
        testDataPeriod, totalSimPeriod, samplesPerHr, MaxHydraulicIter,
        ConvHydraulic, err, lam, rho, mb, mbs, As, Ah, D, L, npipes, fix_G,
        fix_p)

    GlobalSimulationArgsDict = {'cp': cp, 'rho': rho, 'miu': miu, 'L': L,
                                'As': As, 'ts': ts,
                                'fr': fr, 'trunc_ratio': trunc_ratio,
                                'CalNumberFreq': CalNumberFreq,
                                'numberFreq_want': numberFreq_want,
                                'A_thermal': A_thermal,
                                'nnodes': nnodes, 'npipes': npipes,
                                'testDataStep': testDataStep,
                                'simulDataStep': simulDataStep,
                                'steadyTimeBound': steadyTimeBound,
                                'testDataPeriod': testDataPeriod,
                                'totalSimPeriod': totalSimPeriod,
                                'samplesPerHr': samplesPerHr,
                                'MaxHydraulicIter': MaxHydraulicIter,
                                'ConvHydraulic': ConvHydraulic, 'err': err,
                                'lam': lam,
                                'rho': rho, 'mb': mb, 'mbs': mbs, 'As': As,
                                'Ah': Ah, 'D': D,
                                'L': L, 'npipes': npipes, 'fix_G': fix_G,
                                'fix_p': fix_p}

    return GlobalSimulationArgsTuple, GlobalSimulationArgsDict


def global_simulation_args_print(GlobalSimulationArgsD: dict) -> None:
    """打印输出设置的整体仿真参数

    :param GlobalSimulationArgs: 整体仿真参数的字典
    """

    # 采用 PrettyTable Library 打印输出
    table = PrettyTable(['参数名称', '参数设置', '参数单位'])
    table.add_row(['稳态缓冲区时间', str(GlobalSimulationArgsD['steadyTimeBound']), '小时'])
    table.add_row(['历史数据时间间隔', str(GlobalSimulationArgsD['testDataStep']), '秒'])
    table.add_row(['仿真时间间隔', str(GlobalSimulationArgsD['simulDataStep']), '秒'])
    # TODO 添加其他的仿真参数
    print(table)


def HydraulicSimulationArgsCreation(GlobalSimulationArgs, hydraulic_modifiers,
                                    SolverOption: int = 1):
    """
    该函数组合 kv_modifier_input 和返回 GlobalSimulationArgs 中的水力部分
    HydraulicSimulationArgs，是完整水力仿真参数。
    :param GlobalSimulationArgs:
    :param hydraulic_modifiers:
    :param SolverOption:
    :return:
    """

    (cp, rho, miu, L, As, ts, fr, trunc_ratio, CalNumberFreq, numberFreq_want,
     A_thermal, nnodes, npipes, testDataStep,
     simulDataStep, steadyTimeBound, testDataPeriod, totalSimPeriod,
     samplesPerHr, MaxHydraulicIter, ConvHydraulic,
     err, lam, rho, mb, mbs, As, Ah, D, L, npipes, fix_G,
     fix_p) = GlobalSimulationArgs

    HydraulicSimulationArgs = (
        MaxHydraulicIter, ConvHydraulic, hydraulic_modifiers, err, lam, rho, mb,
        mbs, As, Ah, D, L, npipes,
        fix_G, fix_p)

    # HydraulicSimulationArgs = {
    #     'MaxHydraulicIter':GlobalSimulationArgs['MaxHydraulicIter'],
    #     'ConvHydraulic':GlobalSimulationArgs['ConvHydraulic'],
    #     'hydraulic_modifiers':hydraulic_modifiers,
    #     'err':GlobalSimulationArgs['err'],
    #     'lam':GlobalSimulationArgs['lam'],
    #     'rho':GlobalSimulationArgs['rho'],
    #     'mb':GlobalSimulationArgs['mb'],
    #     'mbs':GlobalSimulationArgs['mbs'],
    #     'As':GlobalSimulationArgs['As'],
    #     'Ah':GlobalSimulationArgs['Ah'],
    #     'D':GlobalSimulationArgs['D'],
    #     'L':GlobalSimulationArgs['L'],
    #     'npipes':GlobalSimulationArgs['npipes']
    #                            }

    return HydraulicSimulationArgs


def StaticHydraulicSolver(tabledata, MaxHydraulicIter, ConvHydraulic,
                          hydraulic_modifiers,
                          err, lam, rho, mb, mbs, As, Ah, D, L, npipes, fix_G,
                          fix_p):
    tb1 = tabledata[0]
    tb2 = tabledata[1]
    tb3 = tabledata[2]

    # (kv_modifier_input, kps_modifier_input, fractions_modifiers) = hydraulic_modifiers
    kv_modifier_input = hydraulic_modifiers
    # TODO 采用启发式优化算法来搜寻最优的管道摩擦系数的修正系数
    # 判断几个 valve，并构建 alpha 来修正 kv。
    valveExist = tb2['valve'].fillna(0).to_numpy()
    # amountValves = int(np.max(valveExist))
    # 参考 alpha_input，构建alpha使得最终alpha长度是 npipes
    alpha = np.zeros(npipes)
    # if len(kv_modifier_input) == 1:
    #     alpha[valveExist >=1 ] = kv_modifier_input[0]
    # else:
    #     alpha[valveExist >=1 ] = kv_modifier_input
    alpha[valveExist >= 1] = kv_modifier_input

    # revise lam
    # num_load = int(fractions_modifiers.shape[0])
    # lam[-num_load:] = lam[-num_load:] *(1+fractions_modifiers.squeeze())
    for itera in range(MaxHydraulicIter):  # 最大迭代次数
        # 更新支路参数
        # 各管道集总参数的水阻和水压源参数
        # R 水阻Rh | E 水压源Eh
        R = [lam[i] * mb[i] / rho / As[i] ** 2 / D[i] * L[i] for i in
             range(npipes)]
        E = [-lam[i] * mb[i] ** 2 / 2 / rho / As[i] ** 2 / D[i] * L[i] for i in
             range(npipes)]
        # 追加各支路阀、泵的参数
        for i, row in tb2.iterrows():
            if row.pump > 0:
                kp1, kp2, kp3, w = tb3.loc[
                    f'pump-{int(row.pump)}']  # pump的水力输送导纳特性
                # kp1, kp2, kp3, w = tb3.loc['pump-%d' % int(row.pump), :]  # pump的水力输送导纳特性
                R[i] += -(2 * kp1 * mb[i] + kp2 * w)
                E[i] += (kp1 * mb[i] ** 2 - kp3 * w ** 2)
            if row.valve > 0:
                kv, _, _, _ = tb3.loc[
                    f'valve-{int(row.valve)}']  # valve的水力输送导纳特性
                # kv, _, _, _ = tb3.loc['valve-%d' % int(row.valve), :]  # valve的水力输送导纳特性
                kv = kv * (1 + alpha[i])
                R[i] += 2 * kv * mb[i]  # 2*kv*Gbase
                E[i] -= -kv * mb[i] ** 2
        E = np.array(E).reshape([-1, 1])
        yb = np.diag([1 / Ri for Ri in R])
        # Y = np.matmul(np.matmul(Ah, yb), Ah.T) #Yn
        Y = (Ah @ yb) @ Ah.T  # Yn
        Ygg = Y[fix_G][:, fix_G]  # advanced indexing
        Ygp = Y[fix_G][:, fix_p]
        Ypg = Y[fix_p][:, fix_G]
        Ypp = Y[fix_p][:, fix_p]
        pp = tb1['pressure(MPa)'].values[fix_p].reshape(
            [1, 1]) * 1e6  # vector pn
        # G = tb1['injection(kg/s)'].values.reshape([-1,1]) + np.matmul(np.matmul(Ah, yb), E) # G_prime
        G = tb1['injection(kg/s)'].values.reshape([-1, 1]) + (
                Ah @ yb) @ E  # G_prime
        Gg = G[fix_G, :]
        assert np.linalg.cond(
            Ygg) < 1e5, 'check the initial mass flow rate distribution mb'  # 确认导纳矩阵非奇异
        # pg = np.matmul(np.linalg.inv(Ygg), (Gg - np.matmul(Ygp, pp))) #non-pressurized node pressure change
        pg = np.linalg.inv(Ygg) @ (
                Gg - Ygp @ pp)  # non-pressurized node pressure change
        pn = np.concatenate((pp, pg),
                            axis=0)  # concatenate to get node pressure vector
        # Gb = np.matmul(yb, (np.matmul(Ah.T, pn) - E)) pipe流量
        Gb = yb @ (Ah.T @ pn - E)
        # 添加节点流量计算
        Gn = Ah @ Gb  # @ 就是以前的np.matmul
        err.append(np.linalg.norm(Gb.reshape(-1) - mb))  # 支路平差流量作为收敛条件
        mb = mb * 0.2 + Gb.reshape(
            -1) * 0.8  # 求出来的流量和原来流量的差不是直接加进去的，而是考虑了0.8的权重。
        mbs.append(mb.copy())
        # print('第%d次迭代，失配误差为%.5f'%(itera+1, err[-1]))
        if err[-1] < ConvHydraulic:
            print(f'水力稳态潮流计算迭代{itera + 1}次后收敛。')
            retval = Gb, Gn
            break
        elif itera == MaxHydraulicIter - 1:
            print(f'水力稳态潮流计算迭代次数到达{MaxHydraulicIter}次,未收敛，返回最后一次结果')
            retval = Gb, Gn
    return retval


def ThermalSimulationArgsCreation(tabledata, GlobalSimulationArgs, Gb, Gn,
                                  SolverOption: int = 1):
    """
    该函数返回 ThermalSimulationArgs, OriginalTemperatureBCInput。
    分别是后续动态热力计算需要用到的仿真的参数和输入的边界信息。
    :param tabledata:
    :param GlobalSimulationArgs:
    :param Gb:
    :param Gn:
    :param SolverOption:
    :return:
    """

    (cp, rho, miu, L, As, ts, fr, trunc_ratio, CalNumberFreq, numberFreq_want,
     A_thermal, nnodes, npipes, testDataStep,
     simulDataStep, steadyTimeBound, testDataPeriod, totalSimPeriod,
     samplesPerHr, MaxHydraulicIter, ConvHydraulic,
     err, lam, rho, mb, mbs, As, Ah, D, L, npipes, fix_G,
     fix_p) = GlobalSimulationArgs

    # 管段流量。(npipes,)，array。
    mfr_pipes = Gb.reshape(-1)
    # 节点流量，由稳态水路计算获得。（nnodes,1），vector。（not used）
    mfr_nodes = Gn.reshape([-1, 1])
    weightTopo = CalWeightedTopoMatrices(A_thermal, mfr_pipes)
    # weightTopo = CalWeightedTopoMatrices(GlobalSimulationArgs['A_thermal'], mfr_pipes)
    if SolverOption == 1:
        ThermalSimulationArgs = (
            cp, rho, miu, mfr_pipes, L, weightTopo, As, ts, fr, trunc_ratio,
            CalNumberFreq,
            numberFreq_want)
        OriginalTemperatureBCInput = (
            nnodes, mfr_nodes, npipes, testDataStep, simulDataStep,
            steadyTimeBound,
            testDataPeriod,
            totalSimPeriod, samplesPerHr)
    if SolverOption == 2:
        ThermalSimulationArgs = (cp, rho, miu, mfr_pipes, L, weightTopo, As)
        # laplace求解器，不需要加入steadyTimebound
        OriginalTemperatureBCInput = (
            nnodes, mfr_nodes, npipes, testDataStep, simulDataStep,
            steadyTimeBound,
            testDataPeriod,
            totalSimPeriod, samplesPerHr)

    return ThermalSimulationArgs, OriginalTemperatureBCInput


def ThermalSimulationBCCreation(tabledata, nnodes, m_nodes, npipes,
                                testDataStep,
                                simulDataStep, steadyTimeBound, testDataPeriod,
                                totalSimPeriod, samplesPerHr):
    """
    这函数主要的功能就是针对实际系统中给定的输入热源节点温度(正数)和管段温降(负数)时序
    数据(不一定是24小时的),对其进行增广,加入steadyTimeBound定义的稳定段. 对Fourier变
    换,这一是必不可少的.对Laplace变换,这一步是可选的,并不需要这一步的内容.
    :param tabledata:
    :param nnodes:
    :param m_nodes:
    :param npipes:
    :param testDataStep:
    :param simulDataStep:
    :param steadyTimeBound:
    :param testDataPeriod:
    :param totalSimPeriod:
    :param samplesPerHr:
    :return:
    """

    tb1 = tabledata[0]
    tb2 = tabledata[1]
    tb4 = tabledata[3]
    m_inlet_nodes = np.zeros_like(m_nodes)  # 注入节点流量先都设置为0
    w_inlet_nodes = np.ones_like(m_inlet_nodes)
    # 节点注入温度权重。默认都是1，一般也是1，只有节点有多个注入（注意是注入，不是流入）的情况下， 每个注入的温度权重（ith温度*注入ith流量/总流量）才有意义。
    m_inlet = np.sum(m_nodes[m_nodes > 0])
    # 总注入量, 没用到，只有以后的确节点有多个注入（注意是注入，不是流入）的情况下，才需要和温度权重结合在一起计算。
    TD_Tin = np.zeros([nnodes, totalSimPeriod * samplesPerHr])
    # 论文里的tn，这理论上是要考虑权重，即各节点加权注入温度(注入水流温度乘以注入流量占总流入流量的比例)组成的列向量,
    # 但是一个节点一般就只有一个注入，所以等于权重为1  /
    for i, supply in enumerate(tb1['T(Celsius)'].values):  # suppy这一列的名字就拿出来了
        if isinstance(supply,
                      str):  # 把有string的，就是写了supply1什么的，就识别出来作为输入节点，即节点i是输入节点。
            assert 3600 * testDataPeriod / testDataStep == len(
                tb4[supply])  # 确保tb4[supply]的长度\
            TD_Tin[i, :] = np.concatenate(
                (
                    np.ones(samplesPerHr * steadyTimeBound) *
                    tb4[supply].values[0],
                    np.interp(np.linspace(simulDataStep, 3600 * testDataPeriod,
                                          int(3600 * testDataPeriod / simulDataStep)),
                              np.linspace(testDataStep, 3600 * testDataPeriod,
                                          int(3600 * testDataPeriod / testDataStep)),
                              tb4[supply].values)
                )
            )  # 前steadyTimeBound个小时，没有数据，所以只能都用tb4[supply]第一个数据填充。\
            # 后面的是通过现有的数据进行插值
            w_inlet_node_i = w_inlet_nodes[i]
            TD_Tin[i,
            :] *= w_inlet_node_i  # 这个才是论文的里的 \hat_Tn，目前因为权重为1,基本上等于没有处理。

    # 接下来是负荷导致的温降低，是个负数
    TD_E = np.zeros([npipes, totalSimPeriod * samplesPerHr])
    for i, load in enumerate(tb2.deltaT.values):
        if isinstance(load, str):
            assert 3600 * testDataPeriod / testDataStep == len(
                tb4[load])  # 确保tb4[load]
            TD_E[i, :] = np.concatenate(
                (np.ones(samplesPerHr * steadyTimeBound) * tb4[load].values[0],
                 np.interp(np.linspace(simulDataStep, 3600 * testDataPeriod,
                                       int(3600 * testDataPeriod / simulDataStep)),
                           np.linspace(testDataStep, 3600 * testDataPeriod,
                                       int(3600 * testDataPeriod / testDataStep)),
                           tb4[load].values)
                 )
            )
            # 换热站的温差，如之前讨论，都是放在某个支路上，这支路就是换热器。\
            # 站因此抽象为两部分，一部分是温差，一部分是能量平衡，分开处理。

    retval = TD_Tin, TD_E
    return retval


def FourierTransSolver(TD_Tin, TD_E, cp, rho, miu, mfr_pipes, L_pipes,
                       weightTopo, As_pipes, ts, deltaF, trun_ratio,
                       CalNumberFreq, numberFreq):
    assert np.shape(TD_Tin)[1] == np.shape(TD_E)[1]
    nt = TD_Tin.shape[1]
    # ts: timestep
    # 使用多少个频率，如果fixed_nf_amount，则用给定的numberFreq
    if not CalNumberFreq:
        numberFreqUsed = numberFreq
    # else, 按照给定的辐值截断系数，分别计算TD_Tin，TD_Et的截断频率数目，取大的那个
    else:
        # TD_Tin_freqs = NumberFreqCal(TD_Tin, trun_ratio)
        # TD_Et_freqs = NumberFreqCal(TD_E, trun_ratio)
        # numberFreqUsed = np.max(TD_Et_freqs, TD_Tin_freqs)
        TD_Tin_freqs, TD_Et_freqs = [], []
        for index in range(TD_Tin.shape[0]):
            # 要先判断每一行的数据是否全为零，否则调用NumberFreqCal会报错
            if np.any(TD_Tin[index]):
                TD_Tin_freqs.append(NumberFreqCal(TD_Tin[index], trun_ratio))
        for index in range(TD_E.shape[0]):
            if np.any(TD_E[index]):
                TD_Et_freqs.append(NumberFreqCal(TD_E[index], trun_ratio))
        numberFreqUsed = max(TD_Et_freqs + TD_Tin_freqs)
    # 判断算出来的截断频率是否满足条件
    if numberFreqUsed > nt / 2:  # 考虑了共轭，所以不能超过原始频率数/样本数的一半。
        raise ValueError('numberFreq_want is greater than nf/2 （nt/2）.')
    hA_h_plus, hA_h_min = weightTopo
    numpipes = np.shape(TD_E)[0]  # 默认换热站都在pipe上
    numnodes = np.shape(TD_Tin)[0]  # 温度在节点上
    TD_Tt = np.zeros([numpipes, nt])
    TD_Tf = np.zeros([numpipes, nt])
    FD_Tin = np.zeros([numnodes, numberFreqUsed], dtype='complex_')
    FD_E = np.zeros([numpipes, numberFreqUsed], dtype='complex_')
    Rh = np.array(
        [miu[j] / cp ** 2 / mfr_pipes[j] ** 2 for j in range(numpipes)])  # 支路热阻
    Lh = np.array([rho * As_pipes[j] / cp / mfr_pipes[j] ** 2 for j in
                   range(numpipes)])  # 支路热感
    # time domain to frequency domain conversion
    for i in range(numnodes):
        FD_Tin[i, :] = (fft(TD_Tin[i, :] / nt * 2))[
                       :numberFreqUsed]  # 除以N是因为离散的ft（dft）其反变换的结果如果要换回时域，必须要除一个N
        # 如果是用ifft转换回来，numpy或者说scipy里已经设计好了，就是你不需要考虑这个，直接ifft就行了，他会自己帮你除一个N。但是
        # 我们这里其实不是用ifft转换回来，而是用最后的相位和幅值参与了运算。所以我们最后自己需要除掉这个N。但是为了防止后面忘了除掉N，他
        # 直接就在这里除了N。
        # 因为前半部分和后半部分是conjugate的，所以前半部分参与运算，结果乘以二就行了。但是主要注意的是，这样做的后果就是，0这个地方被加倍了
        # 所以要除掉2
        FD_Tin[i, 0] = FD_Tin[i, 0] / 2
    for i in range(numpipes):
        FD_E[i, :] = (fft(TD_E[i, :] / nt * 2))[:numberFreqUsed]
        FD_E[i, 0] = FD_E[i, 0] / 2

    # frequency domain calculation
    for fi in range(numberFreqUsed):
        f = fi * deltaF
        w = 2 * np.pi * f
        Z = Rh + complex(0, 1) * w * Lh  # 支路传热因子延迟的一部分参数
        K = np.diag([np.exp(-cp * mfr_pipes[j] * Z[j] * L_pipes[j]) for j in
                     range(numpipes)])  # 支路传热因子矩阵，j*j
        assert np.linalg.cond(np.eye(
            numpipes) - K @ hA_h_plus.T @ hA_h_min) < 1e5  # 不能是奇异矩阵，测算condition number
        B = np.linalg.inv(np.eye(numpipes) - K @ hA_h_plus.T @ hA_h_min)
        # 论文里的（I-Kt*Ah+.T*\hat_Ah_)^(-1) # the big inv! jxi, let's call it B
        FD_Tt = B @ (
                (K @ hA_h_plus.T) @ FD_Tin[:, fi].reshape([-1, 1]) + FD_E[:,
                                                                     fi].reshape(
            [-1, 1]))
        # FD_Et和TD_Et都是负数，温降用负数，就不用减掉了。
        # Tt = np.matmul(B, np.matmul(np.matmul(K, A_h_plus.T), FD_Tin[:, fi].reshape([-1, 1])) + FD_E[:, fi].reshape([-1, 1]))
        # Tf = np.matmul(np.linalg.inv(K), Tt - FD_E[:,fi].reshape([-1,1]))
        FD_Tf = np.linalg.inv(K) @ (FD_Tt - FD_E[:, fi].reshape([-1, 1]))
        # FD_Tf = np.linalg.inv(K) @ (FD_Tin[:, fi] - FD_E[:, fi].reshape([-1, 1]))
        # 至此，算出来Tt,Tf的频域分量。把这分量的amplitude和phase都和对应的频率结合起来累加就行了。
        # 频域回时域
        for j in range(numpipes):
            TD_Tt[j, :] += abs(FD_Tt[j, 0]) * np.cos(
                w * ts + phase(FD_Tt[j, 0]))  # 论文2，公式61。和论文3的虚实部结合的公式是\
            # 等同的。这个等同本质上是因为离散傅立叶变换的前后两部分是conjugate的
            TD_Tf[j, :] += abs(FD_Tf[j, 0]) * np.cos(
                w * ts + phase(FD_Tf[j, 0]))
            # 不用再除以N，因为前面已经除了
            # 不用乘以2，因为前面已经乘了。
    # 计算节点温度
    TD_Tnode = hA_h_min @ TD_Tt + TD_Tin
    TD_TtE = TD_Tt - TD_E  # 陈嘉映说的TtE， 就是真实管段末端，模型的管段末端考虑了TD_E（一个负数），要把他减掉才能拿到真实的。
    retval = (TD_Tnode, TD_Tt, TD_Tf, TD_TtE)
    return retval


def FourierResultsParser(
        results):  # TODO Fourier Results Parser 对Fourier 变换，最后的结果需要进行重组来获得真实的数据，需要一个数据处理的函数。

    (TD_Tnode_laplace, TD_Tt_laplace, TD_Tf_laplace, TD_TtE_laplace) = results

    retval = (TD_Tnode_laplace, TD_Tt_laplace, TD_Tf_laplace, TD_TtE_laplace)
    return retval


def LaplaceTransSolver(TD_Tin, TD_Et, cp, rho, miu, mfr_pipes, L_pipes,
                       weightTopo, As_pipes):
    # time domain to complex domain conversion
    # 这个方法的一个不足在于，如果真的要算节点温度变化，你的热源输入必须是可以通过laplace trans变成复域内的。
    # 很多时候其实是没有的。在理想的情况下，比如说指数级的变化下，或者就是一个常数，可以找到对应的变换。
    # 所以只能作为理论分析。实际生活里，只有想办法来拟合一下，让拟合后的结果形式接近可以采用laplace变化的。
    # 但是，从传输问题来说，可以不用考虑输入的profile，这也是好消息。故而虽然下文我也写了CD_Tin 和 CD_Et
    # 但是从计算延迟来说，并不需要这信息，更多是在观察M和V矩阵的结构。
    # 如果真的世纪中我没有进口的显性表达式，但我有一堆他的时序数据，就要你去算末端的温度变化怎么办呢？
    # 答案：这个场景的确不适合用laplace法，还是要用傅立叶变换法去求解。但是如果你真的香浓，想办法把他拟合成一组可以开展
    # laplace变化的函数的线性组合，这样的话，可以帮你找到接近最终结果的显性表达式。
    assert np.shape(TD_Tin)[1] == np.shape(TD_Et)[1]
    s = sym.symbols('s')  # laplace transform in complex domain
    nt = TD_Tin.shape[1]
    [A_h_plus, hA_h_min] = weightTopo

    # convert A_h_plus and hA_h_min from numpy array to sympy Matrix
    A_h_plus = sym.Matrix(A_h_plus)
    hA_h_min = sym.Matrix(hA_h_min)

    numpipes = np.shape(TD_Et)[0]
    numnodes = np.shape(TD_Tin)[0]
    TD_Tt = np.zeros([numpipes, nt])
    TD_Tf = np.zeros([numpipes, nt])
    Rh = sym.Matrix(
        [miu[j] / cp ** 2 / mfr_pipes[j] ** 2 for j in range(numpipes)])  # 支路热阻
    Lh = sym.Matrix([rho * As_pipes[j] / cp / mfr_pipes[j] ** 2 for j in
                     range(numpipes)])  # 支路热感

    # 实际上，这个对仿真没影响，可能对控制设计有影响
    # 因为你无论设置一个什么养的TD_Et， TD_Tin， 热源部分最后你还是要转换回去的，只不过你要考虑热源曲线到了末端的平移和损耗
    # a*exp(-b*s)*CD_Tin(s) 转换回去就是 a*CD_Tin(t-b) 。当然，对TD_Et这项，也是一样的。
    Z = Rh + s * Lh  # 支路传热因子延迟的一部分参数
    # TODO convert K B to sym.Matrix  use numpy.tolist --210804, might not be useful.
    K = sym.Matrix(np.diag(
        [sym.exp(-cp * mfr_pipes[j] * Z[j] * L_pipes[j]) for j in
         range(numpipes)]))  # 支路传热因子矩阵，j*j
    # assert np.linalg.cond(np.eye(A_thermal.shape[1]) - K @ A_h_plus.T @ hA_h_min) < 1e5  # 不能是奇异矩阵，测算condition number
    # @ does matrix multiplication in both NumPy and SymPy for python 3.5+
    # 论文里的（I-Kt*Ah+.T*\hat_Ah_)^(-1) # the big inv! (jxi), let's call it B
    B = (sym.eye(numpipes) - K @ A_h_plus.T @ hA_h_min) ** -1
    # B_ = (sym.eye(numpipes) - K @ A_h_plus.T @ hA_h_min).inv()
    # CD_Tt = B @ (K @ A_h_plus.T @ CD_Tin + CD_Et) pipe outlet temperature
    # CD_Tf = np.linalg.inv(K) @ (CD_Tin - CD_Et) pipe inlet temperature
    # CD_Tnode = hA_h_min @ CD_Tt + CD_Tin node temperature

    # CD_Tnodes = M @ CD_Tin + V @ CD_Et
    # eigen values calculation
    M = hA_h_min @ B @ K @ A_h_plus.T + sym.eye(numnodes)
    V = hA_h_min @ B  # 代码中E是负数，所以V就么有负号。
    retval = (M, V)
    return retval


def LaplaceResultsParser(M: 'sympy matrix', V: 'sympy matrix',
                         TD_Tin: np.ndarray, TD_E: np.ndarray) \
        -> 'nested list':
    """
    :param M:热源符号系数矩阵
    :param V:热用户符号系
    :return: factor_M, factor_V
    """
    # CD_Tnodes = M @ CD_Tin + V @ CD_Et
    # TD_Tnodes = M损耗*TD_Tt(M延迟) +  V损耗*TD_Et(V延迟)
    # 先用sympy.expand()对表达式进行简化,方便后续程序的处理
    # 简化前某些形式如 a1 * (a2 * exp(b2 * s) + a3 * exp(b3 * s) + ...) * exp(b1 * s)
    # 简化后的该形式为 a1' * exp(b1' * s) + a2' * exp(b2' * s) + ...
    # 其中，a1' = a1 * a2, a2' = a1 * a3, b1' = b1 + b2, b2' = b1 + b3, ...
    M = sym.expand(M)
    V = sym.expand(V)
    # 使用正则表达式提取损耗系数和延迟时间
    # 提取字符串中的数字，形式为 xxx[.xxx] 或 -xxx[.xxx]（正数或负数）
    # \d+匹配小数点前数字多次，\.?匹配小数点0次或1次，\d*匹配小数点后数字0次或多次
    # | 表示逻辑或，匹配整数或负数之中的一种形式
    pattern = re.compile(r'\d+\.?\d*|-\d+\.?\d*')
    # 将sympy矩阵转化为numpy矩阵
    M = np.array(M)
    V = np.array(V)
    # 获取 M 和 V 的行数和列数
    row_M, col_M = M.shape
    row_V, col_V = V.shape
    # 记录 M 和 V 的系数，ai代表损耗系数，bi代表延迟时间
    # 创建与 M 和 V 维度相同的嵌套列表
    # 每个元素为一个列表，列表中可添加多个二元元组，形式如下[(a1, b1), (a2, b2), ...]
    # 每个元组中的值分别代表损耗系数和延迟时间,初始化为[(0, 0)]
    factor_M = []
    for index in range(row_M):
        row_factor_M = [[(0, 0)]] * col_M
        factor_M.append(row_factor_M)
    # factor_M的创建方法要按上面的方法，下面的创建方法是错误的
    # 涉及python引用和可变对象背后的原理和陷阱，debug了好久
    # 错误写法：factor_M = [[[(0, 0)]] * col_M] * row_M
    factor_V = []
    for index in range(row_V):
        row_factor_V = [[(0, 0)]] * col_V
        factor_V.append(row_factor_V)
    # 循环迭代，通过正则表达式提取对应的系数，保存到对应的矩阵
    # 对 M 进行处理
    for i in range(row_M):
        for j in range(col_M):
            # 转化为字符串
            string = str(M[i][j])
            # 0表示无关联(0*e^0)，此时矩阵中的元素为[(0, 0)]
            if (string == '0'):
                continue
            # 1表示节点自己，损耗系数为1，延迟时间为0(1*e^0)，此时矩阵中的元素为[(1, 0)]
            elif (string == '1'):
                factor_M[i][j] = [(1, 0)]
            # a1' * exp(b1' * s) + a2' * exp(b2' * s) + ...
            else:
                # 提取string中的所有符合正则表达式pattern的数字，返回一个list L
                # list L中的数字两两一组，前者为损耗系数(ai), 后者为延迟时间(bi)
                L = pattern.findall(string)
                # 将字符串转化为浮点数
                L = [float(x) for x in L]
                factor_M[i][j] = [(L[0], L[1])]
                # 若该节点存在多个热源或热用户节点影响
                if (len(L) // 2) != 1:
                    for k in range(1, len(L) // 2):
                        factor_M[i][j].append((L[2 * k], L[2 * k + 1]))
    # 对 V 进行处理
    for i in range(row_V):
        for j in range(col_V):
            # 转化为字符串
            string = str(V[i][j])
            # 0表示无关联(0*e^0)，此时矩阵中的元素为[(0, 0)]
            if (string == '0'):
                continue
            # 1表示节点自己，损耗系数为1，延迟时间为0(1*e^0)，此时矩阵中的元素为[(1, 0)]
            elif (V[i][j] == 1):
                factor_V[i][j] = [(1, 0)]
            # a1' * exp(b1' * s) + a2' * exp(b2' * s) + ...
            else:
                # 提取string中的所有符合正则表达式pattern的数字，返回一个list L
                # list L中的数字两两一组，前者为损耗系数(ai), 后者为延迟时间(bi)
                L = pattern.findall(string)
                # 将字符串转化为浮点数
                L = [float(x) for x in L]
                if len(L) == 1:
                    factor_V[i][j] = [(L[0], 0)]
                else:
                    factor_V[i][j] = [(L[0], L[1])]
                # 该节点存在多个热源或热用户节点影响
                if (len(L) // 2) != 1:
                    for k in range(1, len(L) // 2):
                        factor_V[i][j].append((L[2 * k], L[2 * k + 1]))

    return factor_M, factor_V


def LaplaceTDTnodei(node_num, factor_M, factor_V, TD_Tin: np.ndarray,
                    TD_E: np.ndarray) \
        -> 'np.ndarray':
    """

    :param node_num: 选取的计算节点序号
    :param factor_M:
    :param factor_V:
    :param TD_Tin:
    :param TD_E:
    :return:
    """
    # 0：初始化操作
    node_num = int(69)
    load_num = int(21)
    time_num = int(300)
    sum_TD_Tin = np.zeros_like(TD_Tin[0])
    sum_TD_E = np.zeros_like(TD_Tin[0])
    TD_Tnodei = np.zeros_like(TD_Tin[0])
    # 1：根据节点的序号提取 factor_M 和 factor_M 中对应的系数
    source_factors_list = factor_M[node_num][0]  # 此处设定 0 是针对目前的一个热源
    user_factors_list = factor_V[node_num][
                        (-1) * load_num:-1]  # 此处设定 -21 是针对目前21个热用户
    # 对 source_factors_list 和 load_factors_list 的类型解释
    # 嵌套列表中的每个列表都对应一个热源和热负荷
    # 每个列表中的每个元组都对应一组热损系数(前)和延迟时间(后)
    # 热损系数为 0~1 的实数，延迟时间为负实数，需要进行取整
    # 2：计算受热源带来温升影响的节点温度时序数列
    t_source0 = TD_Tin[0]  # 1号热源的温度时序数列，Python下标从 0 开始
    for factor_index in range(len(source_factors_list)):
        # 针对时间延迟：数据向后平移，前面不足的数据均赋值为 0 号索引数据值
        trans_num = int(abs(source_factors_list[factor_index][1]) / time_num)
        temp_source_list = [t_source0[0]] * trans_num
        temp_source_list.append(t_source0[trans_num:len(t_source0) - trans_num])
        sum_TD_Tin += np.array(temp_source_list) * \
                      source_factors_list[factor_index][0]
    # 3：计算受热用户带来温降影响的节点温度时序数列
    for user_index in range(len(user_factors_list)):
        if user_factors_list[user_index][0] != 0:
            t_useri = TD_E[user_index]
            trans_num = int(abs(user_factors_list[user_index][1]) / time_num)
            temp_user_list = [t_useri[0]] * trans_num
            temp_user_list.append(t_useri[trans_num:len(t_useri) - trans_num])
            sum_TD_E += np.array(temp_user_list) * \
                        user_factors_list[user_index][0]
    # 4：计算上述两者综合影响的节点温度时序数列
    TD_Tnodei = sum_TD_Tin + sum_TD_E

    return TD_Tnodei


def CalWeightedTopoMatrices(A, mfr_pipes) -> tuple:
    # A：节点支路关联矩阵
    # A_h_plus：即 Ah+(节点–流出支路关联矩阵),支路j从节点i流出,则该元素为1,否则为0.
    A_thermal = A  # 水力、热力共享一个节点支路关联矩阵
    A_h_plus = np.zeros(A_thermal.shape)  # 这个就是论文里的Ah+
    A_h_plus[A_thermal > 0] = 1
    hA_h_min = np.zeros(A_thermal.shape)  # 这个就是论文里的\hat_Ah_
    hA_h_min[A_thermal < 0] = 1
    # A_thermal.shape[0] 就是多少的node
    # A_thermal.shape[1] 就是多少的pipe

    for j in range(A_thermal.shape[1]):
        for i in range(A_thermal.shape[0]):
            hA_h_min[i, j] *= mfr_pipes[j]
    for i in range(A_thermal.shape[0]):
        if sum(hA_h_min[i, :]) == 0:
            continue
        hA_h_min[i, :] /= sum(hA_h_min[i, :])
    weightTopo = A_h_plus, hA_h_min

    return weightTopo


def NumberFreqCal(TSData: np.ndarray, trunc_ratio: float = 5e-3) -> int:
    # 这里输入的应该是 rank 1 array,而不是 nd.array类型的
    # 判断要用几个频率。 当某个频率下的幅值不到直流分量的trunc_ratio时，停止。
    # 把数据都转换为没有维度的ndarray,防止出现了输入进来的是row vector 或者 column vector 或者 无维度的ndarray
    TSData = TSData.squeeze()
    numberFreq_required = int(0)
    # conjugate treatment。共轭部分是对称的，先判断，在前一半的samples里面，到底第几编号的频率开始，他的幅值就不到0频率的trunc_ratio了。之后就用那里的。
    FD_1stHalf = np.split(fft(TSData), 2)[0]  # 分为两部分，取第一部分。
    Invalid_freq_inx = np.flatnonzero(
        abs(FD_1stHalf) / np.max(abs(FD_1stHalf)) < trunc_ratio)
    Trun_freq_inx = np.min(Invalid_freq_inx)

    numberFreq_required = Trun_freq_inx
    # 注意，这里其实减了1.比如说，如果第6号频率（0,1,2,3,4,5,6）的第6个，小于截断频率了，那么我就总共用6个频率（0,1,，3,4,5）
    numberFreqUsed = int(numberFreq_required)

    return numberFreqUsed
