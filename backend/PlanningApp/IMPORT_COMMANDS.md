# PlanningApp Import/Export Commands

## Overview

The PlanningApp provides two management commands:
- `import_production_plan`: Imports production plans from CSV timetables and YAML configuration files
- `export_production_plan`: Exports production plans to CSV timetable format

Both commands work with CSV files in 15-minute interval format, making it easy to import, modify, and re-export production plans.

---

## Import Command

The `import_production_plan` command imports production plans from CSV timetables and YAML configuration files. It automatically detects shifts from the timetable data based on continuous blocks of activity (1's in the CSV).

## Command Usage

```bash
python manage.py import_production_plan <csv_file> <yaml_file> <plan_name> [--clear]
```

### Arguments

- `csv_file`: Path to the CSV timetable file
- `yaml_file`: Path to the YAML configuration file with process properties
- `plan_name`: Name for the production plan to create
- `--clear`: (Optional) Delete existing plan with the same name before importing

## CSV File Format

The CSV file must have the following structure:

- **First column**: `Time` - Timestamp in format `YYYY-MM-DD HH:MM:SS` (15-minute intervals)
- **Other columns**: Process names (must match processes in YAML)
- **Values**: `1` (active) or `0` (inactive)

### Example CSV

```csv
Time,s_finit,s_torre,s_hiro,b_past,b_burr,b_conf
2025-09-22 00:00:00,1,0,0,0,0,0
2025-09-22 00:15:00,1,0,0,0,0,0
2025-09-22 00:30:00,1,0,0,0,0,0
2025-09-22 00:45:00,1,0,0,0,0,0
2025-09-22 01:00:00,1,0,0,0,0,0
...
2025-09-22 06:30:00,1,1,0,0,0,0
2025-09-22 06:45:00,1,1,0,1,0,0
2025-09-22 07:00:00,1,1,0,1,0,0
...
2025-09-22 12:00:00,1,1,1,1,0,0
2025-09-22 12:15:00,1,1,1,1,0,0
2025-09-22 12:30:00,1,1,1,1,1,1
...
```

## YAML File Format

The YAML configuration file specifies process properties:

```yaml
processes:
  process_name:
    electricity_consumption_kWh: <integer>
    max_forward_minutes: <integer, multiple of 5>
    max_backwards_minutes: <integer, multiple of 5>
```

### Example YAML

```yaml
processes: 
  s_finit:
    electricity_consumption_kWh: 50
    max_forward_minutes: 120
    max_backwards_minutes: 50
  s_torre:
    electricity_consumption_kWh: 50
    max_forward_minutes: 120
    max_backwards_minutes: 50
  s_hiro:
    electricity_consumption_kWh: 50
    max_forward_minutes: 120
    max_backwards_minutes: 50    
  b_past:
    electricity_consumption_kWh: 50
    max_forward_minutes: 120
    max_backwards_minutes: 50
  b_burr:
    electricity_consumption_kWh: 50
    max_forward_minutes: 120
    max_backwards_minutes: 50
  b_conf:
    electricity_consumption_kWh: 50
    max_forward_minutes: 120
    max_backwards_minutes: 50
```

## Shift Detection

The command automatically detects shifts by identifying continuous blocks of 1's in the timetable:

- A **shift** starts when a process changes from 0 to 1
- A **shift** continues while consecutive values are 1
- A **shift** ends when a process changes from 1 to 0
- Multiple shifts are created if there are breaks (e.g., `111000111` creates two shifts)

Each shift is automatically named as `<process_name>_shift_<number>`.

## Example Usage

```bash
# Basic import
python manage.py import_production_plan \
    PlanningApp/example_timetable.csv \
    PlanningApp/example_processes_config.yaml \
    "Week 38 Production Plan"

# Import with --clear to replace existing plan
python manage.py import_production_plan \
    PlanningApp/example_timetable.csv \
    PlanningApp/example_processes_config.yaml \
    "Week 38 Production Plan" \
    --clear
```

## Output

The command will output:

```
Created production plan: Week 38 Production Plan
  Created process: s_finit
    Created shift: s_finit_shift_1 (2025-09-22 00:00:00 to 2025-09-22 06:30:00)
  Created process: s_torre
    Created shift: s_torre_shift_1 (2025-09-22 06:30:00 to 2025-09-23 07:30:00)
  Created process: s_hiro
    Created shift: s_hiro_shift_1 (2025-09-22 07:45:00 to 2025-09-23 03:15:00)
  Created process: b_past
    Created shift: b_past_shift_1 (2025-09-22 06:45:00 to 2025-09-22 08:00:00)
    Created shift: b_past_shift_2 (2025-09-22 10:00:00 to 2025-09-22 15:30:00)
    Created shift: b_past_shift_3 (2025-09-23 07:30:00 to 2025-09-23 10:15:00)
  Created process: b_burr
    Created shift: b_burr_shift_1 (2025-09-22 07:30:00 to 2025-09-22 12:15:00)
    Created shift: b_burr_shift_2 (2025-09-22 12:30:00 to 2025-09-22 14:45:00)
    Created shift: b_burr_shift_3 (2025-09-23 07:30:00 to 2025-09-23 10:15:00)
  Created process: b_conf
    Created shift: b_conf_shift_1 (2025-09-22 08:00:00 to 2025-09-22 12:15:00)
    Created shift: b_conf_shift_2 (2025-09-22 12:30:00 to 2025-09-22 14:45:00)
    Created shift: b_conf_shift_3 (2025-09-23 07:30:00 to 2025-09-23 10:15:00)

Import complete:
  Production plan: Week 38 Production Plan
  Processes created: 6
  Shifts created: 17
```

## Validation

The command performs the following validations:

- **File existence**: Checks that both CSV and YAML files exist
- **Process matching**: Ensures all processes in CSV are defined in YAML and vice versa
- **YAML format**: Validates YAML structure
- **CSV format**: Validates timestamp format

## Transaction Safety

The import is wrapped in a database transaction (`@transaction.atomic`), ensuring that:

- If any error occurs, no changes are committed to the database
- The operation is all-or-nothing (atomic)
- Database consistency is maintained

## Notes

- The CSV must use 15-minute intervals (as shown in the example)
- All timestamps must be in `YYYY-MM-DD HH:MM:SS` format
- Process names in CSV and YAML must match exactly
- The `max_forward_minutes` and `max_backwards_minutes` apply to all shifts of a process
- Values in CSV must be either 0 or 1

---

## Export Command

The `export_production_plan` command exports a production plan to CSV format with the same structure as the import CSV format.

### Command Usage

```bash
python manage.py export_production_plan <plan_name> <output_file> [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD]
```

### Arguments

- `plan_name`: Name of the production plan to export
- `output_file`: Path where the CSV file will be written
- `--start-date`: (Optional) Start date for the timetable in `YYYY-MM-DD` format
- `--end-date`: (Optional) End date for the timetable in `YYYY-MM-DD` format

If `--start-date` and `--end-date` are not provided, the command automatically calculates the date range based on the shifts in the production plan.

### Output Format

The exported CSV has the same structure as the import format:

```csv
Time,s_finit,s_torre,s_hiro,b_past,b_burr,b_conf
2025-09-22 00:00:00,1,0,0,0,0,0
2025-09-22 00:15:00,1,0,0,0,0,0
2025-09-22 00:30:00,1,0,0,0,0,0
...
```

- **First column**: `Time` - Timestamp in format `YYYY-MM-DD HH:MM:SS` (15-minute intervals)
- **Other columns**: Process names from the production plan (sorted alphabetically)
- **Values**: `1` (shift active) or `0` (shift inactive)

### Example Usage

```bash
# Export with automatic date range detection
python manage.py export_production_plan "Week 38 Production Plan" output_plan.csv

# Export with specific date range
python manage.py export_production_plan \
    "Week 38 Production Plan" \
    output_plan.csv \
    --start-date 2025-09-22 \
    --end-date 2025-09-28
```

### Example Output

```
Found production plan: Week 38 Production Plan
Date range: 2025-09-22 to 2025-09-23

Export complete:
  Output file: output_plan.csv
  Processes: 6
  Rows written: 145
  Time range: 2025-09-22 00:00:00 to 2025-09-23 10:00:00
```

### Use Cases

1. **Backup**: Export production plans for backup or version control
2. **Modification**: Export, modify in a spreadsheet, and re-import
3. **Analysis**: Export for analysis in other tools (Excel, Python, R, etc.)
4. **Comparison**: Export different plans to compare timetables
5. **Documentation**: Generate readable timetables for documentation

### Notes on Export

- Processes are sorted alphabetically in the CSV columns
- The export generates 15-minute interval rows
- Time range is automatically calculated from shifts if not specified
- Shifts are converted to 0/1 values based on whether they're active at each timestamp
- The export is compatible with the import command format

---

## Complete Workflow Example

Here's a complete workflow showing import, export, and re-import:

```bash
# 1. Import original plan
python manage.py import_production_plan \
    original_timetable.csv \
    processes_config.yaml \
    "Original Plan"

# 2. Export the plan
python manage.py export_production_plan \
    "Original Plan" \
    exported_plan.csv

# 3. Modify exported_plan.csv in a spreadsheet

# 4. Import the modified plan (needs YAML config)
python manage.py import_production_plan \
    exported_plan.csv \
    processes_config.yaml \
    "Modified Plan"
```

This workflow allows for easy iteration and refinement of production plans using familiar spreadsheet tools.
