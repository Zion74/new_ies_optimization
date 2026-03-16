------

**Title:** Optimal Configuration of Distributed Electric-Heating-Cooling Integrated Energy System Considering Source-Load Matching with Energy Quality Difference

Abstract:

Current capacity planning strategies for Integrated Energy Systems (IES) typically evaluate source-load matching based solely on the quantitative balance of energy supply and demand. This approach neglects the fundamental difference in energy quality (exergy) among electricity, heat, and cold, leading to inefficient system configurations. To address this, this paper proposes a novel source-load matching quantification method based on energy quality coefficient-weighted Euclidean distance. First, based on the Second Law of Thermodynamics, Carnot factors are introduced to define the energy quality coefficients for heat and cold relative to electricity, establishing a unified evaluation benchmark. Second, a coupled matching index is constructed using Euclidean distance to penalize simultaneous multi-energy imbalances. This index is integrated into a bi-level planning model alongside economic objectives. A case study based on a regional IES in Germany demonstrates that, compared to traditional fluctuation-based methods, the proposed approach effectively guides the system toward energy cascade utilization. It significantly improves exergy efficiency and reduces high-quality energy waste while maintaining economic viability.

**Keywords:** Integrated Energy System; Capacity Planning; Source-Load Matching; Exergy Analysis; Energy Quality.

------

## 1. Introduction

The transition towards low-carbon energy systems has accelerated the development of Distributed Integrated Energy Systems (IES). By coupling electricity, heat, and cooling networks, IES achieves high efficiency through multi-energy complementarity. Reasonable capacity configuration is the prerequisite for the economic and stable operation of IES.

Existing literature on IES planning predominantly focuses on economic indicators, such as minimizing the Annualized Total Cost (ATC). To enhance system autonomy and reduce grid dependence, "Source-Load Matching" (SLM) has become a critical constraint or objective. Traditional SLM indicators, such as the overlap ratio or net load fluctuation rate, focus on smoothing the energy exchange curve. However, these methods are fundamentally based on the First Law of Thermodynamics, assuming that 1 kWh of electricity, heat, and cold hold equal physical value.

From the perspective of the Second Law of Thermodynamics (Exergy), this assumption is flawed. Electricity is pure exergy (high-quality), whereas low-temperature heat and cold are low-quality energies with limited work potential. Ignoring this disparity often leads to "high-quality energy low-use" scenarios—for example, configuring oversized electric storage to smooth inexpensive thermal load fluctuations.

To overcome these limitations, this paper proposes an optimal configuration method for Electric-Heating-Cooling IES considering energy quality differences. The main contributions are:

1. **Unified Evaluation Benchmark:** Energy quality coefficients are defined based on Carnot theory to convert heterogeneous energies into equivalent "electricity value."
2. **Novel Matching Index:** A weighted Euclidean distance index is proposed to capture and penalize simultaneous imbalances in multi-energy flows.
3. **Bi-level Optimization:** A planning-operation bi-level model is established to balance thermodynamic perfection and economic costs.

------

## 2. System Modeling

### 2.1 System Architecture

The object of this study is a grid-connected Distributed Electric-Heating-Cooling (EHC) system. As shown in **[Insert Fig. 1: System Topology]**, the system comprises:

- **Energy Supply:** Photovoltaic (PV), Wind Turbines (WT), Utility Grid, and Natural Gas Network.
- **Energy Conversion:** Gas Turbines (GT) for Combined Cooling, Heating, and Power (CCHP); Absorption Chillers (AC) for waste heat recovery; Electric Chillers (EC) and Heat Pumps (HP) for electrical-to-thermal conversion.
- **Energy Storage:** Battery Energy Storage (ES), Heat Storage (HS), and Cool Storage (CS).

### 2.2 Equipment Modeling

Standard mathematical models are adopted for the conversion and storage devices. The operational efficiency of the Gas Turbine and the Coefficient of Performance (COP) for chillers and heat pumps are assumed to be constant values under nominal conditions for the planning stage.

------

## 3. Proposed Methodology

### 3.1 Definition of Energy Quality Coefficients

To quantify the "quality" of different energy forms, this paper introduces the Energy Quality Coefficient ($\lambda$). Based on the Carnot theorem, $\lambda$ represents the ratio of the theoretical maximum work potential (exergy) relative to the reference environment state ($T_0$).

Considering the nominal design conditions of the industrial park:

- Reference Temperature: $T_0 = 298.15 \text{ K} (25^\circ \text{C})$.
- Heating Supply Temperature: $T_{heat} = 343.15 \text{ K} (70^\circ \text{C})$.
- Cooling Supply Temperature: $T_{cool} = 280.15 \text{ K} (7^\circ \text{C})$.

The coefficients are calculated as follows:

1. **Electricity ($\lambda_e$):** As pure exergy, $\lambda_e = 1.0$.
2. **Heat ($\lambda_h$):** $\lambda_h = 1 - T_0 / T_{heat} \approx 0.13$.
3. **Cold ($\lambda_c$):** $\lambda_c = (T_0 - T_{cool}) / T_{cool} \approx 0.06$.

The values indicate that electricity holds the highest physical value, followed by heat and cold. This hierarchy forms the basis for the "High-quality for High-use" principle.

### 3.2 Coupled Source-Load Matching Index

Traditional statistical indices (e.g., standard deviation) assess the fluctuation of individual energy streams independently. In contrast, this paper proposes a **Coupled Matching Index ($F_{match}$)** based on energy-quality-weighted Euclidean distance. It is defined as the average cumulative magnitude of the net load vector in the "Value Space" over the planning period $T$:

$$F_{match} = \frac{1}{T} \sum_{t=1}^{T} \sqrt{ (\lambda_e P_{net,e}^t)^2 + (\lambda_h P_{net,h}^t)^2 + (\lambda_c P_{net,c}^t)^2 }$$

Where $P_{net,i}^t$ represents the absolute net interaction (mismatch) with the external grid for energy $i$ at time $t$. The Euclidean distance non-linearly amplifies the penalty for **simultaneous imbalances** (e.g., simultaneous shortage of electricity and heat), guiding the optimization algorithm to select coupling devices (like GT+AC) that can resolve multi-dimensional mismatches.

------

## 4. Optimization Model

A bi-level optimization framework is established:

- **Upper Level (Planning):** Uses the NSGA-II algorithm to optimize the capacity of the 9 types of equipment.
  - *Objective 1:* Minimize Annualized Total Cost (ATC), including investment, O&M, fuel, and grid electricity costs (incorporating a two-part tariff).
  - *Objective 2:* Minimize the proposed Source-Load Matching Index ($F_{match}$).
- **Lower Level (Operation):** Uses Mixed-Integer Linear Programming (MILP) to optimize hourly dispatch strategies for minimum operating cost.

------

## 5. Case Study and Results Analysis

### 5.1 Parameter Setup

The proposed method is validated using data from a regional IES in Germany. The load profiles and meteorological data are typical for an industrial park with consistent cooling/heating demands. The electricity price follows a two-part tariff structure: a capacity price of **[Insert Data]** €/kW·a and an energy price of **[Insert Data]** €/kWh. Equipment parameters are detailed in **[Insert Table 1]**.

### 5.2 Optimization Results

The Pareto front obtained by NSGA-II is shown in **[Insert Fig. 2: Pareto Front]**. A clear trade-off is observed: improving the matching degree (lowering $F_{match}$) requires increased economic investment.

To evaluate the superiority of the proposed method, three typical schemes are selected for comparison:

- **Scheme A:** Economic-optimal solution (Single objective).
- **Scheme B:** Optimal solution based on the traditional **Net Load Fluctuation Rate (Standard Deviation)** metric.
- **Scheme C:** Optimal solution based on the **Proposed Energy Quality Matching** metric (Trade-off point).
- Capacity Configuration Analysis

The capacity configuration results are presented in [Insert Table 2].

Comparing Scheme B and Scheme C reveals significant differences in equipment selection:

- **Scheme B (Traditional)** tends to configure large capacities for **Cool Storage (CS)** and **Electric Chillers (EC)**. This is because the fluctuation-based metric treats cold load smoothing as equally important as electrical load smoothing, leading to excessive investment in low-grade energy storage.
- **Scheme C (Proposed)** configures larger capacities for **Gas Turbines (GT)** and **Absorption Chillers (AC)**, while reducing EC and CS capacities.
  - *Reasoning:* Due to the high weight of electricity ($\lambda_e=1$), Scheme C prioritizes electrical self-sufficiency via GT. Simultaneously, to minimize the "waste heat penalty," the system naturally couples GT with AC. This realizes the cascade utilization of "Power Generation + Waste Heat Cooling," avoiding the thermodynamic penalty of using high-quality electricity for low-quality cooling (via EC).
- Performance Metrics Analysis

The thermodynamic and economic performance indicators are summarized in [Insert Table 3].

It is noteworthy that **Scheme C achieves the highest Exergy Efficiency**. Although Scheme B reduces the fluctuation of energy exchange, it achieves this by downgrading high-quality electricity into low-quality cold energy for storage. In contrast, Scheme C, guided by exergy coefficients, optimizes the quality-matching of energy conversion, resulting in a higher primary energy utilization rate and lower thermodynamic loss.

### 5.3 Operational Strategy Analysis

To illustrate the coupling mechanism, the energy balance of Scheme C on a typical summer day is analyzed, as shown in **[Insert Fig. 3: Summer Operation Profile]**.

During peak electrical load hours (e.g., **[Insert Time]**), the GT operates at near-full capacity to reduce grid dependence. Crucially, the substantial waste heat produced is fully absorbed by the AC to meet the cooling load, significantly reducing the operation of the EC. This "Heat-to-Cooling" mode demonstrates that the proposed index successfully drives the system to adopt an operation strategy that aligns with the Second Law of Thermodynamics.

------

## 6. Conclusion

This paper proposes a capacity configuration method for electric-heating-cooling IES considering source-load matching with energy quality differences. The conclusions are as follows:

1. The introduction of Carnot-based energy quality coefficients ($\lambda_e=1, \lambda_h \approx 0.13, \lambda_c \approx 0.06$) effectively corrects the physical bias in traditional planning that equates electricity with heat/cold.
2. The proposed coupled matching index successfully guides the configuration towards **cascade utilization technologies** (e.g., CCHP with Absorption Chillers), avoiding irrational over-investment in low-grade energy storage merely for fluctuation smoothing.
3. Comparative results indicate that the proposed method significantly improves the system's **exergy efficiency** while maintaining economic competitiveness, verifying its value in promoting high-quality development of integrated energy systems.

Future work will investigate the impact of dynamic environmental temperatures on energy quality coefficients and explore the integration of novel Carnot Battery technologies.

------

**[End of Manuscript]**