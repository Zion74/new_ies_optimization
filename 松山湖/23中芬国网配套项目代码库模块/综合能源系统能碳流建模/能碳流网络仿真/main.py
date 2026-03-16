# -*- coding: utf-8 -*-
from Energy_to_exergy import Energy2exergy
from CEF_modeling import CEF_modeling
import warnings
"""
本py文件针对binhai_data_working_condition_1.xlsx中的一个时间切片数据进行计算。
同时这一时间切片也是论文中展示的计算
"""
# ”能“到”㶲“的转换部分
E2Ex = Energy2exergy(path=f"binhai_data_working_condition_1.xlsx", T_ambient=20 + 273.15, P_ambient=0.1, working_medium="steam")
CEF_modeling = CEF_modeling(path=f"binhai_data_working_condition_1.xlsx", T_ambient=20 + 273.15, P_ambient=0.1, working_medium="steam")
flows = E2Ex.branch_calculate() # 能源网络潮流计算结果
exergy_node = E2Ex.energy2exergy_steam() # 能源网络节点的㶲 J/kg
exergy_branch = {
        id_in_run :
    [
        exergy_node.loc[E2Ex.df_branch.loc[id_in_run,"From节点号"],"exergy_node J/kg"]*flows.loc[id_in_run,"flow（kg/s）"]/1000000,
        exergy_node.loc[E2Ex.df_branch.loc[id_in_run,"To节点号"],"exergy_node J/kg"]*flows.loc[id_in_run,"flow（kg/s）"]/1000000
    ]
    for id_in_run in E2Ex.df_branch.index
} # 能源网络边的㶲 W
exergy_node_source_inject = {
    node_id:-E2Ex.df_node.loc["flow（kg/s）",node_id]*exergy_node.loc[node_id,"exergy_node J/kg"]/1000000
    for node_id in E2Ex.source_node_id_set
} # 机组注入节点的㶲 W
exergy_load = {
    node_id:flows.loc[E2Ex.node_flowin_branch_id[node_id][0],"flow（kg/s）"]*exergy_node.loc[node_id,"exergy_node J/kg"]/1000000
    for node_id in E2Ex.load_node_id_set
} # 负荷的㶲 W

# 碳流建模部分
p, p_genertor, p_load, A, A_1, p_gross, p_load_gross, p_loss_gross, p_itoj_branch= CEF_modeling.up_A(exergy_branch, exergy_node_source_inject) # 碳流建模关键矩阵
table_load_gross_decompose, table_loss_gross_decompose = CEF_modeling.load_track(p, p_genertor, p_load, A, A_1, p_gross, p_load_gross, p_loss_gross, p_itoj_branch, exergy_branch, exergy_load)
table_branch_gross_decompose_flowin, table_branch_gross_decompose_loss, table_branch_gross_decompose_flowout = CEF_modeling.branch_track(p, p_genertor, p_load, A, A_1, p_gross, p_load_gross, p_loss_gross, p_itoj_branch, exergy_branch, exergy_load)

# 碳流建模结果
Carbon_table_branch_gross_decompose_flowin = CEF_modeling.carbon_flow(table=table_branch_gross_decompose_flowin, carbon_emission_factor = [0.85, 0.7])
Carbon_table_branch_gross_decompose_loss = CEF_modeling.carbon_flow(table=table_branch_gross_decompose_loss, carbon_emission_factor = [0.85, 0.7])
Carbon_table_branch_gross_decompose_flowout = CEF_modeling.carbon_flow(table=table_branch_gross_decompose_flowout, carbon_emission_factor = [0.85, 0.7])