# 烟厂第三场景

该目录由 课题组场景整理模板_烟厂_清洗版.xlsx 导出，用于验证 	obacco_factory_multi_energy 场景走 uture_generic 通用后端。

- scenario.yaml: 标准场景配置。
- 	ypical_profiles.csv: 12 个月典型日的电、冷、蒸汽负荷。
- input_resource_profiles.csv: 电网、天然气、太阳辐射、余热、温度输入/资源曲线。
- data_gaps.csv: 数据来源与缺口说明。

该场景不走旧版 current_cchp，用于工业蒸汽、余热回收、热泵和储热等通用模块接口验证。
