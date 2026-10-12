"""Train / retrain the tabular risk models from the bundled CSVs.

    python train_model.py            # both models
    python train_model.py heart      # UCI Cleveland only
    python train_model.py diabetes   # Pima Indians only

The API retrains automatically on start-up if an artifact is missing or was
built with a different scikit-learn version, so running this is optional.
"""
import sys

from app import ml

if __name__ == "__main__":
    keys = sys.argv[1:] or list(ml.SPECS)
    for key in keys:
        payload = ml.train(key)
        print(f"{key}: {payload['metrics']}  -> {ml.SPECS[key]['path']}")
