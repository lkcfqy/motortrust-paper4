# Paper 4 data attribution and license notice

This notice narrows the original MotorTrust dataset attribution to the two Paper 4 sources. It makes no new license declaration for independently authored MotorTrust code or manuscripts.

| Component | Source and attribution | License |
| --- | --- | --- |
| Electric Motor Temperature, source 52 kW PMSM | Kirgsn (`wkirgsn`), [Kaggle](https://www.kaggle.com/datasets/wkirgsn/electric-motor-temperature), DOI [10.34740/KAGGLE/DSV/2161054](https://doi.org/10.34740/KAGGLE/DSV/2161054), local source version 3 | CC BY-SA 4.0; original text in `CC-BY-SA-4.0.txt` |
| LPTN-informed LSTM IPMSM dataset / upstream repository | [Zirui24/lptn_informed_LSTM](https://github.com/Zirui24/lptn_informed_LSTM), frozen commit `98e4566b5fb7c70499996fda18dd73179ec16509`; Copyright (c) 2024 Zirui Liu; related article by Liu, Kong, Fan, Li, Peng and Qu, DOI [10.1109/TPEL.2024.3409388](https://doi.org/10.1109/TPEL.2024.3409388) | MIT; original text in `MIT-LPTN-Liu-2024.txt` and `data/raw/lptn_informed_lstm/LICENSE` |

Raw data files are excluded from Git. Source provenance and the upstream README/license are retained. MotorTrust preprocessing harmonizes node semantics, reduces source sampling from 2 Hz to 1 Hz and applies frozen profile splits. When redistributing adapted source-dataset material, preserve attribution, identify these changes and follow applicable CC BY-SA terms. Preserve the MIT notice when distributing upstream external files.

License information above is carried forward from the original MotorTrust snapshot and its frozen configuration; this split does not relicense independently authored work.
