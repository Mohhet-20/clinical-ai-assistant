# UCI dataset provenance and attribution

The `uci-heart-disease.zip` archive is the official UCI Machine Learning Repository Heart Disease dataset, dataset 45. The `uci-source/processed.cleveland.data` source file is used to make `cleveland.csv` via `prepare_dataset.py`. The included `models/heart-risk.joblib` is trained from that prepared CSV using `train_model.py`.

Dataset citation:

> Janosi, A., Steinbrunn, W., Pfisterer, M., & Detrano, R. (1989). Heart Disease [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C52P4X

UCI lists the dataset under Creative Commons Attribution 4.0 International (CC BY 4.0). The Cleveland cohort has 303 instances and 13 published predictors; target values 0–4 describe angiographic disease presence, with common demonstrations grouping values 1–4 together. Some feature values are missing. The preparation script keeps missing values as `?`; the training script drops rows containing missing feature or target values.

This historical clinical dataset is for educational model workflow demonstration. It is not a representative current population, does not measure future event risk, and does not establish clinical performance. The included holdout results are exploratory only.
