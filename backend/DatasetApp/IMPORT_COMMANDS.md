# DatasetApp Import Commands

The easiest way to load data is the admin: open the dataset (or add a new one) and upload the CSV
file. The same import is available from the command line:

```bash
python manage.py import_generation_records  <csv_file> <dataset_name> [--clear] [--skip-validation]
python manage.py import_prices_records      <csv_file> <dataset_name> [--clear] [--skip-validation]
python manage.py import_temperature_records <csv_file> <dataset_name> [--clear] [--skip-validation]
```

- `dataset_name`: the dataset is created if it does not exist.
- `--clear`: delete the existing records of the dataset first (otherwise existing hours are updated
  and new hours are added).
- `--skip-validation`: accept files with missing hours (not recommended: missing hours count as 0).

The whole file is checked before anything is stored: if a row is invalid, nothing is imported and
the error names the line.

## CSV formats

One row per hour. `Time` accepts `YYYY-MM-DD HH:MM:SS`, `YYYY-MM-DD HH:MM`, `DD-MM-YYYY HH:MM:SS`
and `DD/MM/YYYY HH:MM[:SS]`, in local time (Europe/Rome). Other columns are ignored (for example
the old `methane_prices` column).

```csv
Time,cogen_kWh,solar_kWh
2024-01-01 00:00:00,0,0
```

```csv
Time,electricity_price
2024-01-01 00:00:00,0.18325
```

```csv
Time,outside_temperature
2024-01-01 00:00:00,6.8
```

Generation values are kWh produced in the hour (i.e. average kW); prices are €/kWh and cannot be
negative.
