# document.extract_pairs_csv

Extract simple label-number pairs from a local PDF and write them as a CSV.

## Usage

```bash
document.extract_pairs_csv /workspace/drinks_survey.pdf /workspace/drinks_survey.csv --col1 drink --col2 quantity
```

Use `--col1` and `--col2` to set CSV headers.

## Environment

No service credentials are required.

## Side Effects

Reads a local PDF and writes a local CSV file.
