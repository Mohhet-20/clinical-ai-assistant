"""Prepare the official processed Cleveland flat file into a named CSV.

Source: UCI Heart Disease dataset, CC BY 4.0. The raw UCI file has 14
comma-separated columns and no header. Missing values are preserved as '?'
for the training script to handle.
"""
import argparse
import csv
from pathlib import Path

RAW_COLUMNS = ["age", "sex", "cp", "trestbps", "chol", "fbs", "restecg", "thalach", "exang", "oldpeak", "slope", "ca", "thal", "target"]


def main() -> None:
    root = Path(__file__).parent
    parser = argparse.ArgumentParser()
    parser.add_argument("source", nargs="?", type=Path, default=root / "data" / "uci-source" / "processed.cleveland.data")
    parser.add_argument("--output", type=Path, default=root / "data" / "cleveland.csv")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with args.source.open(newline="", encoding="utf-8") as source, args.output.open("w", newline="", encoding="utf-8") as dest:
        writer = csv.writer(dest)
        writer.writerow(RAW_COLUMNS)
        for row_number, row in enumerate(csv.reader(source), start=1):
            if not row or all(not value.strip() for value in row):
                continue
            if len(row) != len(RAW_COLUMNS):
                raise ValueError(f"Expected 14 columns on raw line {row_number}, found {len(row)}")
            writer.writerow([value.strip() for value in row])
            count += 1
    if count == 0:
        raise ValueError("No dataset rows found")
    print(f"Prepared {count} rows with {len(RAW_COLUMNS) - 1} features: {args.output}")


if __name__ == "__main__":
    main()
