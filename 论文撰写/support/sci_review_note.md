## Overall Impression

This is a well-structured, publication-ready manuscript for Applied Energy. The writing quality is high — clear, precise, and follows IMRAD conventions well. The two-contribution structure (exergy-weighted matching index + Carnot battery integration) is logically coherent, and the "closed validation loop" framing is a strong narrative device.

## Strengths

1. The Introduction is excellent — it builds a clear funnel from CCHP background → matching indices → exergy gap → Carnot battery gap → contributions, with well-integrated citations. The positioning against existing exergy-based work (Li 2022, Chen 2024, Ma 2023, Duo 2025) is precise and differentiating.
2. The matching index section (Section 3) is the paper's strongest part. The thermodynamic derivation is rigorous, the "parameter-free" argument is compelling, and Table 2 (index property comparison) is an effective summary. The paragraph explaining why small λ_h/λ_c values are a feature, not a bug, is particularly well-argued.
3. The post-optimization analysis methodology (budget increment alignment) is a smart design choice — it answers the practical question "what do I get for each additional euro?" rather than just comparing Pareto fronts abstractly.
4. The machine learning analogy (matching index as loss function, operational indicators as evaluation metrics) in the Discussion is insightful and accessible.

## Issues to Address

### Substantive

1. The abstract is 280+ words and reads as a single dense paragraph. Applied Energy accepts structured abstracts, but even for unstructured ones, consider splitting into 2 paragraphs for readability. More importantly, the abstract front-loads methodology and back-loads results — for a top journal, lead with the key finding (6.1× wider Pareto front, 26.7% lower peak demand) earlier.
2. Experiments 3 and 4 (Carnot battery ablation and joint validation) are mentioned in [case_studies.tex](vscode-webview://057pgic6sk8inon32q35r2at0c22cah0mjl9tfckc8h6hfm8q8if/%E8%AE%BA%E6%96%87%E6%92%B0%E5%86%99/paper/sections/case_studies.tex) Table 4 but their results are absent from [results.tex](vscode-webview://057pgic6sk8inon32q35r2at0c22cah0mjl9tfckc8h6hfm8q8if/%E8%AE%BA%E6%96%87%E6%92%B0%E5%86%99/paper/sections/results.tex). The Results section only covers Experiments 1 and 2. This is a significant gap — the Carnot battery is billed as a co-equal contribution but lacks dedicated results.
3. The Songshan Lake results (Experiment 2) show EQD has 18.9% curtailment vs. Std's 1.0%. The paper acknowledges this but hand-waves it ("curtailed PV can be absorbed by EV charging"). A reviewer will push back here. Consider quantifying the economic cost of curtailment or discussing it more rigorously in the Discussion.
4. The German electricity price of €0.0025/kWh looks suspiciously low — that's 0.25 cents/kWh. Typical German industrial rates are €0.15–0.25/kWh. If this is correct (perhaps a wholesale or internal transfer price), it needs explicit justification. A reviewer will flag this.

### References

1. Several BibTeX entries have year mismatches with their cite keys:
  - `liu2018combined` → actual year 2014
  - `wang2019multi` → actual year 2015
  - `ren2010optimal` → actual year 2008
  - `cho2009combined` → actual year 2014
  - `sakulpipatsin2010exergy` → actual year 2018
  - `torchio2013comparison` → actual year 2015
  These won't cause compilation errors but make the .bib file confusing to maintain.
2. `wang2018review` appears to be about shale gas reservoirs, not energy systems — likely a wrong entry. Check if it's actually cited anywhere.
3. `li2021comprehensive` is about electric vehicles — also likely unused or wrong.

### Structural / Formatting

1. No figures are referenced with actual image files. The topology diagram (`\Cref{fig:topology}`), Pareto comparison plots, and operational analysis charts are all missing. For Applied Energy, you'll need 5–8 figures minimum.
2. The Conclusions section could be tighter. The first two paragraphs largely repeat the abstract and results. Focus on what's new — the implications and limitations.
3. The CRediT statement uses placeholder names ("First Author", "Second Author"). Minor, but easy to forget before submission.

### Minor

1. In [system_modeling.tex:84](vscode-webview://057pgic6sk8inon32q35r2at0c22cah0mjl9tfckc8h6hfm8q8if/%E8%AE%BA%E6%96%87%E6%92%B0%E5%86%99/paper/sections/system_modeling.tex#L84), the storage equation uses $P_s^{\text{dis}}(t)/\eta_s^{\text{dis}}$ — this means discharging *increases* the stored energy denominator, which is the correct convention (energy out of storage = stored energy × efficiency), but double-check this matches your oemof implementation.
2. The `\si{\text{\euro}/(kW \cdot a)}` usage in [optimization.tex](vscode-webview://057pgic6sk8inon32q35r2at0c22cah0mjl9tfckc8h6hfm8q8if/%E8%AE%BA%E6%96%87%E6%92%B0%E5%86%99/paper/sections/optimization.tex) is non-standard for siunitx — consider defining a custom unit.

---

## Priority Actions

The most critical item is writing the missing Experiments 3 & 4 results. Without them, the Carnot battery contribution is unsupported. Second priority is adding figures. Third is fixing the suspicious electricity price or adding justification.

The writing itself is strong — this reads like a near-final draft, not a first attempt. Nice work.