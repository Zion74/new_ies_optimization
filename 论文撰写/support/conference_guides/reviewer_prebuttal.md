# Reviewer Prebuttal for the IEEE Conference Draft

This note lists the most likely reviewer questions for the current conference manuscript and the recommended response line. The goal is to keep the conference claim narrow, evidence-based, and easy to defend.

## 1) "Why is IEMI better if its matching-index values are numerically larger than Std?"

**Likely concern.** The reviewer notices that IEMI values are in the 600--2200 range while Std values are around 400--530 and suspects the comparison is inconsistent.

**Recommended response.** The paper does not claim that the absolute values of the two objectives are directly comparable. Std and IEMI are different metrics on different numerical scales. The manuscript therefore compares:

- the reachable cost span of the non-dominated set;
- the shape of the front after within-method normalization; and
- 8760-hour operational outcomes of budget-aligned designs.

**Where addressed in the paper.**
- `sections_conference/results.tex`: normalized Pareto figure and the "Scope and threats to validity" subsection.

## 2) "Is the reported advantage simply because the IEMI solution spends more money?"

**Likely concern.** At `+100%` budget allowance the selected IEMI design costs about 869 kEUR, while Std saturates around 637 kEUR.

**Recommended response.** The comparison is intentionally framed as a **budget-allowance** test relative to the economic optimum, not as a strict equal-spend dominance claim. The result supports the statement that IEMI unlocks a richer high-investment design region that Std fails to reach, not that every IEMI point dominates every Std point at the same absolute cost.

**Where addressed in the paper.**
- `sections_conference/case_studies.tex`: explicit selection protocol.
- `sections_conference/results.tex`: clarification that actual selected costs differ across methods.

## 3) "Does IEMI dominate Std across the whole budget range?"

**Likely concern.** A reviewer may test whether the method helps only in a cherry-picked high-budget scenario.

**Recommended response.** No, and the paper now says this explicitly. In the current benchmark, Std remains slightly better at low budget allowances (`+10%`, `+30%`), while IEMI overtakes from the medium-to-high budget region onward. This makes the claim more credible: IEMI is presented as a method that expands the **high-investment trade-off space**, not as a universally dominant objective.

**Where addressed in the paper.**
- `main_conference.tex`: abstract tempered accordingly.
- `sections_conference/results.tex`: budget-sweep figure and discussion.

## 4) "Why is Std the main baseline? Why not Pearson, SSR, or more metrics?"

**Likely concern.** The reviewer worries that the baseline may be chosen because it is easy to beat.

**Recommended response.** Std is retained because it is the **closest structural baseline** to IEMI: both use the same three carrier net-imbalance series and the same cost-plus-matching optimization framework, differing mainly in whether coupling is handled instantaneously or after carrier-wise compression. Pearson and SSR are valid archived alternatives, but they quantify different notions of coordination and would dilute the conference paper's methodological focus.

**Where addressed in the paper.**
- `sections_conference/case_studies.tex`: baseline-selection paragraph.

## 5) "Are the results actually driven by the carrier weights rather than by the Euclidean geometry?"

**Likely concern.** The reviewer suspects that the apparent gain may come from exergy-like weighting instead of the vector formulation.

**Recommended response.** The paper keeps the carrier weights fixed within the benchmark and frames the conference claim narrowly: under one documented weight setting, instantaneous vector coupling changes the structure of the planning front. A broader sensitivity study over carrier weights belongs to the journal extension. If needed in rebuttal, you can mention that an archived unit-weight exploratory run also preserved the qualitative trend of a wider Euclidean front, but that exploratory result is not part of the formal conference evidence set.

**Where addressed in the paper.**
- `sections_conference/matching_index.tex`: fixed-weight explanation.
- `sections_conference/conclusions.tex`: future-work statement.

## 6) "How robust is this result to representative-day approximation and GA randomness?"

**Likely concern.** The reviewer questions whether the observed gap is an artifact of clustering or a single stochastic optimization run.

**Recommended response.** The current conference evidence is based on one documented full run (`N_ind=50`, `G_max=100`) and 14 representative days. The paper already mitigates one part of that concern by re-dispatching selected designs over the full 8760-hour year, so the operational conclusions do not rely solely on representative days. However, multi-seed robustness and broader aggregation sensitivity are deliberately stated as future work rather than claimed as resolved.

**Where addressed in the paper.**
- `sections_conference/optimization.tex`: warm-start and robustness limitation.
- `sections_conference/results.tex`: "Scope and threats to validity".

## 7) "The benchmark electricity price seems unrealistically low. Are the absolute capacity recommendations meaningful?"

**Likely concern.** The reviewer notices that the tariff setup is benchmark-specific and may not represent a current German retail or distribution tariff.

**Recommended response.** The manuscript now states clearly that the tariff values are archived benchmark inputs and not a present-day market calibration. The paper's claim is methodological and comparative: under the same fixed benchmark inputs, IEMI changes the planning-to-operation trade-off structure. The absolute capacity mix should therefore be interpreted as benchmark-specific rather than universally prescriptive.

**Where addressed in the paper.**
- `sections_conference/case_studies.tex`: benchmark-tariff caution.
- `sections_conference/results.tex`: threats-to-validity paragraph.

## 8) "Does warm-starting IEMI from Std make the comparison unfair?"

**Likely concern.** The reviewer worries that IEMI benefits from a better initial population.

**Recommended response.** Warm start is used only as a computational acceleration device. It does not change the feasible region, the objective function, or the search budget. The key empirical observation is that IEMI continues to generate distinct high-investment trade-offs after Std has already saturated, which is hard to explain as initialization alone. Still, a no-warm-start ablation is a reasonable journal-stage robustness check and is now named as future work.

**Where addressed in the paper.**
- `sections_conference/optimization.tex`: explicit clarification.

---

## Suggested oral defense summary

If the discussion becomes compressed, use this short summary:

> This conference paper does not claim that IEMI dominates all other objectives at all budgets or under all tariffs. The claim is narrower: when we keep the benchmark, devices, and optimization budget fixed, replacing carrier-wise temporal compression with instantaneous three-carrier vector coupling materially enlarges the accessible high-investment planning region, and that difference survives 8760-hour re-dispatch in the form of lower grid dependence.
