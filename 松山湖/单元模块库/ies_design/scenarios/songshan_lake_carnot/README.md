# 松山湖卡诺电池扩展场景

这是第三个真实可计算场景，用于中期接口第二版验证。

- 数据来源：复用 `data/songshan_lake_data.csv` 和 `data/songshan_lake_typical.xlsx`。
- 系统结构：`cchp_ehc_carnot`，在松山湖基础 CCHP 上增加卡诺电池。
- 结构差异：除 PV、CHP、热泵、电制冷、吸收式制冷和冷热电储能外，新增卡诺电池功率和能量容量变量。
- 求解后端：`current_cchp`，可真实运行 `demo`、`quick` 等模式。

验证命令：

```powershell
rtk uv run python design.py --scenario "松山湖\单元模块库\ies_design\scenarios\songshan_lake_carnot\scenario.yaml" --mode demo
```

