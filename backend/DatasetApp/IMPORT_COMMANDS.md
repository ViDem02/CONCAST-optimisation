# DatasetApp Import Commands

Django management commands for importing CSV data into the DatasetApp.

## Available Commands

### 1. Import Generation Records

Import electricity generation data (solar and cogenerator).

**Command:**
```bash
python manage.py import_generation_records <csv_file> <dataset_name> [--clear]
```

**Arguments:**
- `csv_file`: Path to the CSV file
- `dataset_name`: Name of the GenerationDataset (must exist)
- `--clear`: Optional flag to delete existing records before importing

**CSV Format:**
```csv
Time,cogen_kWh,solar_kWh
2024-01-01 00:00:00,0,0
2024-01-01 01:00:00,0,0
2024-01-01 02:00:00,0,1
```

**Example:**
```bash
# Create the dataset first (via Django admin or API)
python manage.py import_generation_records data/gen_2024.csv "Generation 2024"

# Import and clear existing data
python manage.py import_generation_records data/gen_2024.csv "Generation 2024" --clear
```

---

### 2. Import Prices Records

Import electricity and methane prices.

**Command:**
```bash
python manage.py import_prices_records <csv_file> <dataset_name> [--clear]
```

**Arguments:**
- `csv_file`: Path to the CSV file
- `dataset_name`: Name of the PricesDataset (must exist)
- `--clear`: Optional flag to delete existing records before importing

**CSV Format:**
```csv
Time,electricity_price,methane_prices
2024-01-01 00:00:00,0.18325,0.04958
2024-01-01 01:00:00,0.18025,0.04958
2024-01-01 02:00:00,0.17625,0.04958
```

**Example:**
```bash
# Create the dataset first (via Django admin or API)
python manage.py import_prices_records data/prices_2024.csv "Prices 2024"

# Import and clear existing data
python manage.py import_prices_records data/prices_2024.csv "Prices 2024" --clear
```

---

### 3. Import Temperature Records

Import outside temperature data.

**Command:**
```bash
python manage.py import_temperature_records <csv_file> <dataset_name> [--clear]
```

**Arguments:**
- `csv_file`: Path to the CSV file
- `dataset_name`: Name of the TemperatureDataset (must exist)
- `--clear`: Optional flag to delete existing records before importing

**CSV Format:**
```csv
Time,outside_temperature
01-01-2024 00:00:00,12.2
01-01-2024 01:00:00,11.8
01-01-2024 02:00:00,11.4
```

**Note:** Supports both date formats:
- `01-01-2024 00:00:00` (dd-mm-yyyy)
- `2024-01-01 00:00:00` (yyyy-mm-dd)

**Example:**
```bash
# Create the dataset first (via Django admin or API)
python manage.py import_temperature_records data/temp_2024.csv "Temperature 2024"

# Import and clear existing data
python manage.py import_temperature_records data/temp_2024.csv "Temperature 2024" --clear
```

---

## Workflow

1. **Create the dataset** (via Django admin or API):
   ```bash
   # Via Django shell
   python manage.py shell
   >>> from DatasetApp.models import GenerationDataset
   >>> GenerationDataset.objects.create(name="Generation 2024", is_active=True)
   ```

2. **Import the CSV data**:
   ```bash
   python manage.py import_generation_records data/gen_2024.csv "Generation 2024"
   ```

3. **Verify the import**:
   - Check Django admin at `/admin/`
   - Or use the API at `/api/datasets/generation-records/`

---

## Features

- **Update or Create**: Records are updated if they already exist (based on dataset + timestamp)
- **Error Handling**: Continues processing even if individual rows fail
- **Clear Option**: `--clear` flag removes all existing records before import
- **Summary Report**: Shows count of created, updated, and error records
- **Validation**: Checks for required CSV headers before processing

---

## Error Handling

If a row fails to import, the command will:
- Display the error message with row number
- Continue processing remaining rows
- Show total errors in the final summary

Common errors:
- Invalid date format
- Missing required columns
- Invalid numeric values
- Dataset doesn't exist

---

## Performance Tips

For large CSV files (>10,000 rows):
- Use `--clear` flag to avoid duplicate checking overhead
- Consider importing in batches if memory is limited
- Run migrations before importing: `python manage.py migrate`
