# Paper 4 literature-gap audit

## Bottom line

The crowded part of this topic is temperature-model architecture. The defensible opening is not
another claim that physics plus a neural network improves RMSE on one motor. It is an auditable test
of whether electrothermal state models and their uncertainty survive transport to a second physical
PMSM when selection is profile-disjoint and external outcomes are frozen.

## Closest work and consequence for positioning

| Prior work | What already exists | What Paper 4 must not claim | Remaining auditable gap |
|---|---|---|---|
| Kirchgässner et al., EAAI 2023, `10.1016/j.engappai.2022.105537` | Thermal neural networks that embed LPTN-style state evolution; 52 kW public dataset and code | First physics-guided neural thermal state model | Cross-physical-machine transport, profile-level uncertainty, and support-aware failure reporting |
| Liu et al., IEEE TPEL 2024, `10.1109/TPEL.2024.3409388` | LPTN-informed LSTM for multi-node temperature estimation and the second public IPMSM dataset | First LPTN-informed neural model or first use of this target dataset | Use the dataset only after a source protocol is frozen; compare source prior, target-only prefix, and source-prior calibration |
| Zhang et al., NPSIF 2024, `10.1109/NPSIF64134.2024.10883597` | GAN augmentation plus unsupervised domain adaptation for transferable PM-temperature estimation | First cross-motor transfer method | Closed-loop grey-box transport with transparent target-label budget, complete-profile splits, uncertainty, and rejection |
| Shafieeroudbari et al., ICEM 2024, `10.1109/ICEM60801.2024.10700124` | Incremental deep learning for real-time rotor-temperature estimation | First online/incremental thermal update | Source-prior versus target-only identifiability and an untouched second-machine stress test |
| Gao et al., Machines 2026, `10.3390/machines14020138` | Bayesian self-calibration plus a hierarchical physics-aware network and safety-margin monitoring | First adaptive/self-evolving PMSM digital twin | Reproducible transport benchmarking with public raw data, leakage guards, failed-gate reporting, and profile-level intervals |
| Zhu et al., Applied Thermal Engineering 2026, `10.1016/j.applthermaleng.2026.132461` | Dynamic/static topology thermal network and hot-spot forecasting, including a public-data evaluation | First dynamic-topology physics-informed PMSM estimator | Predeclared second-machine transfer and explicit differentiation between within-machine generalization and machine transport |

## Frozen novelty statement

Paper 4 contributes a reproducible experimental protocol and evidence, not a claim of architectural
primacy. It will:

1. harmonize two public, physically distinct PMSMs into a documented three-node state contract;
2. compare frozen source, target-only prefix, and source-prior prefix calibration under identical
   recursive rollouts;
3. keep the 14 source-test and 16 external profiles out of all model/hyperparameter selection;
4. calibrate simultaneous trajectory bands on complete source-validation profiles rather than
   treating time samples as exchangeable;
5. flag source-support violations without deleting them from primary results; and
6. publish negative transfer or failed uncertainty coverage as primary evidence if the gates fail.

The strongest defensible title form is a question (“Do electrothermal models transport?”), not a
superiority claim. A positive result would support limited five-minute commissioning adaptation;
a negative result would quantify why within-machine RMSE does not certify cross-machine deployment.

