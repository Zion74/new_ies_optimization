# -*- coding: utf-8 -*-

import numpy as np
import pandas as pd
import CoolProp.CoolProp as CP
from param import DataFrame


class CEF_modeling():
    """"
        本方法主要针对能源网络中的节点、边、负荷求解碳排放强度，即carbon emission flow建模。
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
        self.df_node = pd.read_excel(self.path, sheet_name=f"{self.working_medium}_load", header=0,
                                     index_col=0)  # 读取对应能源网络的负荷信息
        self.df_branch = pd.read_excel(self.path, sheet_name=f"{self.working_medium}_branch", header=0,
                                       index_col=0)  # 读取对应能源网络的连接关系
        self.num_load_node = (self.df_node.loc["flow（kg/s）", :] > 0).sum()  # 负荷节点数量
        self.num_source_node = (self.df_node.loc["flow（kg/s）", :] < 0).sum()  # 源节点数量
        self.num_intermediate_node = (self.df_node.loc["flow（kg/s）", :] == 0).sum()  # 中间节点数量，中间节点意为未接入机组和负荷的节点
        self.num_node = len(self.df_node.columns)  # 节点总数量
        self.num_branch = len(self.df_branch.index)  # 边总数量
        self.load_node_id_set = [node_id for node_id in self.df_node.columns if
                                 self.df_node.loc["flow（kg/s）", node_id] > 0]  # 负荷节点的id集合
        self.source_node_id_set = [node_id for node_id in self.df_node.columns if
                                   self.df_node.loc["flow（kg/s）", node_id] < 0]  # 源节点的id集合
        self.intermediate_node_id_set = [node_id for node_id in self.df_node.columns if
                                         self.df_node.loc["flow（kg/s）", node_id] == 0]  # 中间节点的id集合
        self.node_flowin_branch_id = {
            node_id: self.df_branch[self.df_branch.loc[:, "To节点号"] == node_id].index.to_list()
            for node_id in self.df_node.columns
        }  # dict, 用于查询一个节点的流入边的id
        self.node_flowout_branch_id = {
            node_id: self.df_branch[self.df_branch.loc[:, "From节点号"] == node_id].index.to_list()
            for node_id in self.df_node.columns
        }  # dict, 用于查询一个节点的流出边的id
        self.node_id_couple_for_branch = {branch_id: self.df_branch.loc[branch_id, :].to_list()
                                          for branch_id in self.df_branch.index
                                          }  # dict, 用于查询一个节点连接的所有的边的id


    def up_A(self, exergy_branch, exergy_node_source_inject):
        """
        获得进行碳流建模的关键矩阵
        :param exergy_branch:
        :param exergy_node_source_inject:
        :return:
        """
        p = []
        for node_id in self.df_node.columns:
            key_list = self.node_flowin_branch_id[node_id]
            p.append(sum(exergy_branch[key][1] for key in key_list) + exergy_node_source_inject.get(node_id, 0))
        p_genertor = [exergy_node_source_inject.get(node_id,0) for node_id in self.df_node.columns]
        A = np.eye(self.num_node)
        for branch_id in self.df_branch.index:
            to_node_id = self.df_branch.loc[branch_id,"To节点号"]
            from_node_id = self.df_branch.loc[branch_id,"From节点号"]
            A[to_node_id-1, from_node_id-1] = - exergy_branch[branch_id][0]/p[from_node_id-1]
        p_load = [exergy_branch[self.node_flowin_branch_id[node_id][0]][1] if node_id in self.load_node_id_set else 0 for node_id in self.df_node.columns]
        A_1 = np.linalg.inv(A)
        p_gross = np.dot(A_1, p_genertor)
        p_load_gross = [p_load[i]*np.dot(A_1[i,:],p_genertor)/p[i] for i in range(self.num_node)]
        p_loss_gross = list(map(lambda x,y:x-y,p_load_gross,p_load))
        p_itoj_branch = {}
        for node_idi in self.df_node.columns:
            intermediate_list = []
            for node_idj in self.df_node.columns:
                mask = (self.df_branch.loc[:, "From节点号"]==node_idi) & (self.df_branch.loc[:, "To节点号"]==node_idj)
                if mask.sum():
                    intermediate_list.append(exergy_branch[self.df_branch[mask].index.tolist()[0]][0])
                else:
                    intermediate_list.append(0)
            p_itoj_branch[node_idi] = intermediate_list
            # p_itoj_branch = pd.DataFrame(p_itoj_branch)
        return p, p_genertor, p_load, A, A_1, p_gross, p_load_gross, p_loss_gross, p_itoj_branch

    def load_track(self, p, p_genertor, p_load, A, A_1, p_gross, p_load_gross, p_loss_gross, p_itoj_branch, exergy_branch, exergy_load):
        # 先求比例系数proportion_load
        table_load_gross_decompose = np.zeros((self.num_node, self.num_node))
        for i in range(self.num_node):
            for j in range(self.num_node):
                table_load_gross_decompose[i, j] = p_load_gross[i] * A_1[i, j] * p_genertor[j] / p_gross[i]
        rows_to_keep = ~np.all(table_load_gross_decompose == 0, axis=1)
        cols_to_keep = ~np.all(table_load_gross_decompose == 0, axis=0)
        table_load_gross_decompose = table_load_gross_decompose[rows_to_keep, :][:, cols_to_keep]
        row_sums = table_load_gross_decompose.sum(axis=1)
        table_load_gross_decompose = np.column_stack((table_load_gross_decompose,row_sums))
        table_load_gross_decompose = pd.DataFrame(table_load_gross_decompose,
                             index=[f"load(node)MW: #{node_id}" for node_id in self.load_node_id_set],
                             columns=[f"generator(node)MW: #{node_id}" for node_id in self.source_node_id_set] + ["SUM MW"])
        proportion = table_load_gross_decompose.loc[:,f"generator(node)MW: #{self.source_node_id_set[0]}":f"generator(node)MW: #{self.source_node_id_set[-1]}"]
        self.proportion_load = np.array(proportion.div(table_load_gross_decompose["SUM MW"], axis=0))

        # 再求table_load_gross_decompose
        keys = sorted(exergy_load.keys())
        values = [exergy_load[key] for key in keys]
        values_array = np.array(values).reshape(-1, 1)  # 将值转换为列向量
        result = self.proportion_load * values_array
        row_sums = result.sum(axis=1)
        table_load_gross_decompose = np.column_stack((result, row_sums))
        table_load_gross_decompose = pd.DataFrame(table_load_gross_decompose,
                             index=[f"load(node)MW: #{node_id}" for node_id in self.load_node_id_set],
                             columns=[f"generator(node)MW: #{node_id}" for node_id in self.source_node_id_set] + ["SUM MW"])

        # 再求table_loss_gross_decompose
        p_loss_gross_without_zero = np.array([i for i in p_loss_gross if i !=0])
        table_loss_gross_decompose =proportion * p_loss_gross_without_zero[:, np.newaxis]
        row_sums = table_loss_gross_decompose.sum(axis=1)
        table_loss_gross_decompose_array = table_loss_gross_decompose.values
        row_sums_array = row_sums.values
        table_loss_gross_decompose_array = np.hstack((table_loss_gross_decompose_array, row_sums_array[:, np.newaxis]))
        table_loss_gross_decompose = pd.DataFrame(table_loss_gross_decompose_array,
                                                  index=table_load_gross_decompose.index,
                                                  columns=table_load_gross_decompose.columns)
        return table_load_gross_decompose, table_loss_gross_decompose

    def branch_track(self, p, p_genertor, p_load, A, A_1, p_gross, p_load_gross, p_loss_gross, p_itoj_branch, exergy_branch, exergy_load):
        # 先求比例系数proportion_load
        table_branch_gross_decompose = []
        for i in range(self.num_node):
            for j in range(self.num_node):
                if p_itoj_branch[i+1][j] != 0:
                    table_branch_gross_decompose.append(
                        [p_itoj_branch[i+1][j] * (A_1[i, k] * p_genertor[k]) / p[i] for k in range(self.num_node)])
        table_branch_gross_decompose = np.array(table_branch_gross_decompose)[:,[0,1]]
        row_sums = table_branch_gross_decompose.sum(axis=1)
        table_branch_gross_decompose = np.column_stack((table_branch_gross_decompose,row_sums))
        table_branch_gross_decompose = pd.DataFrame(table_branch_gross_decompose,
                             index=[f"branch(flowin)MW: #{branch_id}" for branch_id in self.df_branch.index],
                             columns=[f"generator(node)MW: #{node_id}" for node_id in self.source_node_id_set] + ["SUM MW"])
        proportion = table_branch_gross_decompose.loc[:,f"generator(node)MW: #{self.source_node_id_set[0]}":f"generator(node)MW: #{self.source_node_id_set[-1]}"]
        self.proportion_branch = np.array(proportion.div(table_branch_gross_decompose["SUM MW"], axis=0))

        # 再求table_branch_gross_decompose_flowin
        keys = sorted(exergy_branch.keys())
        values = [exergy_branch[key][0] for key in keys]
        values_array = np.array(values).reshape(-1, 1)  # 将值转换为列向量
        result = self.proportion_branch * values_array
        row_sums = result.sum(axis=1)
        table_branch_gross_decompose_flowin = np.column_stack((result, row_sums))
        table_branch_gross_decompose_flowin = pd.DataFrame(table_branch_gross_decompose_flowin,
                             index=[f"branch(flowin)MW: #{branch_id}" for branch_id in range(1, self.num_branch+1)],
                             columns=[f"generator(node)MW: #{node_id}" for node_id in self.source_node_id_set] + ["SUM MW"])

        # 再求table_branch_gross_decompose_flowout
        keys = sorted(exergy_branch.keys())
        values = [exergy_branch[key][1] for key in keys]
        values_array = np.array(values).reshape(-1, 1)  # 将值转换为列向量
        result = self.proportion_branch * values_array
        row_sums = result.sum(axis=1)
        table_branch_gross_decompose_flowout = np.column_stack((result, row_sums))
        table_branch_gross_decompose_flowout = pd.DataFrame(table_branch_gross_decompose_flowout,
                             index=[f"branch(flowout)MW: #{branch_id}" for branch_id in range(1, self.num_branch+1)],
                             columns=[f"generator(node)MW: #{node_id}" for node_id in self.source_node_id_set] + ["SUM MW"])

        # 再求table_branch_gross_decompose_loss
        table_branch_gross_decompose_loss = np.array(table_branch_gross_decompose_flowin)- np.array(table_branch_gross_decompose_flowout)
        table_branch_gross_decompose_loss = pd.DataFrame(table_branch_gross_decompose_loss,
                                                            index=[f"branch(loss)MW: #{branch_id}" for branch_id in
                                                                   range(1, self.num_branch + 1)],
                                                            columns=[f"generator(node)MW: #{node_id}" for node_id in
                                                                     self.source_node_id_set] + ["SUM MW"])
        return table_branch_gross_decompose_flowin, table_branch_gross_decompose_loss, table_branch_gross_decompose_flowout

    def carbon_flow(self, table, carbon_emission_factor):
        carbon_emission_factor = np.array(carbon_emission_factor)
        table.iloc[:, :-1] = table.iloc[:, :-1].multiply(carbon_emission_factor, axis=1)
        table.iloc[:, -1] = table.iloc[:, :-1].sum(axis=1)
        return table