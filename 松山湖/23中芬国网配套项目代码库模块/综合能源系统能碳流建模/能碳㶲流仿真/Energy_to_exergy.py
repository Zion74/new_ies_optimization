# -*- coding: utf-8 -*-

import numpy as np
import pandas as pd
import CoolProp.CoolProp as CP
from param import DataFrame


class Energy2exergy():
    """"
    本方法主要针对碳流建模中可能涉及到的非电能源形式进行”能“到”㶲“的转换。
    Attributes:
        path(str): 需要输入的excel表的项目相对路径。如“binhai_data_working_condition_1.xlsx”
        T_ambient(float): 环境温度 单位：K
        P_ambient(float): 环境压力 单位：MPa
        work_medium(str)：需要进行”能“到”㶲“的转换的能源形式，如”steam“、”compressed_air“
    """
    def __init__(self, path, T_ambient, P_ambient, working_medium: str):
        self.path = path
        self.T_ambient = T_ambient
        self.P_ambient = P_ambient
        self.working_medium = working_medium
        self.df_node = pd.read_excel(self.path, sheet_name=f"{self.working_medium}_load", header=0, index_col=0) # 读取对应能源网络的负荷信息
        self.df_branch = pd.read_excel(self.path, sheet_name=f"{self.working_medium}_branch", header=0, index_col=0) # 读取对应能源网络的连接关系
        self.num_load_node = (self.df_node.loc["flow（kg/s）",:] > 0).sum() # 负荷节点数量
        self.num_source_node = (self.df_node.loc["flow（kg/s）",:] < 0).sum() # 源节点数量
        self.num_intermediate_node = (self.df_node.loc["flow（kg/s）",:] == 0).sum() # 中间节点数量，中间节点意为未接入机组和负荷的节点
        self.num_node = len(self.df_node.columns) # 节点总数量
        self.num_branch = len(self.df_branch.index) # 边总数量
        self.load_node_id_set = [node_id for node_id in self.df_node.columns if self.df_node.loc["flow（kg/s）", node_id] > 0] # 负荷节点的id集合
        self.source_node_id_set = [node_id for node_id in self.df_node.columns if self.df_node.loc["flow（kg/s）", node_id] < 0] # 源节点的id集合
        self.intermediate_node_id_set = [node_id for node_id in self.df_node.columns if self.df_node.loc["flow（kg/s）", node_id] == 0] # 中间节点的id集合
        self.node_flowin_branch_id = {
            node_id : self.df_branch[self.df_branch.loc[:, "To节点号"] == node_id].index.to_list()
            for node_id in self.df_node.columns
        } # dict, 用于查询一个节点的流入边的id
        self.node_flowout_branch_id = {
            node_id : self.df_branch[self.df_branch.loc[:, "From节点号"] == node_id].index.to_list()
            for node_id in self.df_node.columns
        } # dict, 用于查询一个节点的流出边的id
        self.node_id_couple_for_branch = {branch_id : self.df_branch.loc[branch_id,:].to_list()
            for branch_id in self.df_branch.index
        } # dict, 用于查询一个节点连接的所有的边的id

    def branch_calculate(self):
        """
        对能源网络全网的潮流迭代。
        return:
            DataFrame: 每一个边的流量
        """
        # Identify known and unknown branches
        known_branches = [self.df_branch[self.df_branch['To节点号'] == node].index[0] for node in self.df_node.columns if self.df_node.at["flow（kg/s）", node] > 0]
        unknown_branches = [id for id in self.df_branch.index if id not in known_branches]

        # Initialize branch flows
        branch_flows = pd.DataFrame(
            [self.df_node.at["flow（kg/s）", to_node_id] if self.df_node.at["flow（kg/s）", to_node_id] > 0 else 0
             for to_node_id in self.df_branch['To节点号']],
            index=self.df_branch.index, columns=['flow（kg/s）']
        )

        # Iteratively calculate unknown branch flows
        while True:
            temp_branch_flows = branch_flows.copy()
            for node_id in self.df_node.columns:
                out_branches = self.df_branch[self.df_branch['From节点号'] == node_id].index.tolist()
                in_branches = self.df_branch[self.df_branch['To节点号'] == node_id].index.tolist()

                if (set(in_branches).issubset(unknown_branches) and
                        in_branches and
                        out_branches and
                        set(out_branches).issubset(known_branches)):
                    total_flow = branch_flows.loc[out_branches, 'flow（kg/s）'].sum()
                    if self.df_node.loc["flow（kg/s）",node_id] < 0:
                        branch_flows.loc[in_branches, 'flow（kg/s）'] = total_flow + self.df_node.loc["flow（kg/s）",node_id]
                    else:
                        branch_flows.loc[in_branches, 'flow（kg/s）'] = total_flow
                    unknown_branches.remove(in_branches[0])
                    known_branches.append(in_branches[0])

            if temp_branch_flows.equals(branch_flows):
                break
        return branch_flows


    def energy2exergy_steam(self):
        """
        对蒸汽网络的节点的㶲进行计算。
        return:
            DataFrame: 每一个节点的㶲，J/kg
        """
        # 定义常数
        T_network = 350 + 273.15  # 张淑婷师姐毕业论文的恒定温度假设，全网恒温 单位：K
        P_node = self.df_node.loc["pressure（MPa）"].values * 1000000  # 获取Series中的单个值并转换为Pa

        # 计算全网节点和环境的蒸汽焓和蒸汽熵
        S_network = CP.PropsSI("S", "P", P_node, "T", T_network, "water")
        S_ambient = CP.PropsSI("S", "P", self.P_ambient * 1000000, "T", self.T_ambient, "water")
        H_network = CP.PropsSI("H", "P", P_node, "T", T_network, "water")
        H_ambient = CP.PropsSI("H", "P", self.P_ambient * 1000000, "T", self.T_ambient, "water")

        # 计算全网节点的蒸汽㶲 (J/kg)
        exergy_steam_node = (H_network - H_ambient) - self.T_ambient * (S_network - S_ambient)
        exergy_steam_node = pd.DataFrame(exergy_steam_node, index = self.df_node.columns, columns=["exergy_node J/kg"])
        return exergy_steam_node

    def energy2exergy_compressed_air(self):
        """
        对压缩空气网络的节点的㶲进行计算。
        return:
            DataFrame: 每一个节点的㶲，J/kg
        """
        # 定义常数
        P_node = self.df_node.loc["pressure（MPa）"].values * 1000000  # 获取Series中的单个值并转换为Pa

        # 计算全网节点和环境的压缩空气焓和压缩空气熵
        S_network = CP.PropsSI("S", "P", P_node, "T", self.T_ambient, "air")
        S_ambient = CP.PropsSI("S", "P", self.P_ambient * 1000000, "T", self.T_ambient, "air")
        H_network = CP.PropsSI("H", "P", P_node, "T", self.T_ambient, "air")
        H_ambient = CP.PropsSI("H", "P", self.P_ambient * 1000000, "T", self.T_ambient, "air")

        # 计算全网节点的蒸汽㶲 (J/kg)
        exergy_compressed_air_node = (H_network - H_ambient) - self.T_ambient * (S_network - S_ambient)
        exergy_compressed_air_node = pd.DataFrame(exergy_compressed_air_node, index = self.df_node.columns, columns=["exergy_node J/kg"])
        # 计算各管道的蒸汽㶲
        return exergy_compressed_air_node

    def energy2exergy_nature_gas_as_flue(self, heat_value):
        """"
        和压缩空气与蒸汽不同，天然气作为燃料其燃烧释放的化学能（㶲）远远大于静压、动压等（㶲）。所以按照热值计算㶲流
        单位：本方法中的df_node的流量为体积流量（km3/h，140psi，281.15k），全网的压缩空气流量都以这个状态下的压缩空气的体积流量表示
        热值：和单位一样，热值也是140psi，281.15k下的热值，热值单位为：MWh/km3
        return:
            DataFrame: 每一个节点的㶲，J/kg
        """
        exergy_compressed_air_node = np.ones((self.num_node,1))*heat_value*3600*1000000
        exergy_compressed_air_node = pd.DataFrame(exergy_compressed_air_node, index = self.df_node.columns, columns=["exergy_node J/kg"])
        # 计算各节点的天然气㶲
        return exergy_compressed_air_node