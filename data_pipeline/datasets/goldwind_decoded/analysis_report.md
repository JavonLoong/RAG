# Goldwind Decoding And Data Quality Report

## Outputs

- Decoded database: `goldwind_decoded\GW15000120180104.db`
- Parsed CSV: `goldwind_decoded\parsed_data.csv`
- Split column files: `goldwind_decoded\columns`
- Column manifest: `goldwind_decoded\column_manifest.csv`
- JSON report: `goldwind_decoded\analysis_report.json`

## Required Checks

- File existence: PASS, `parsed_data.csv` exists.
- Data shape: 12098 rows x 190 columns from table `RUNDATA`.
- Numeric conversion: 186 columns can be converted to numeric values; 4 columns contain non-numeric values.
- Missing values: PASS, no missing values detected.

## Missing Value Handling Plan

No missing values were found in the current file. If future files contain missing values, use median or timestamp-aware interpolation for numeric sensor data, mode or forward-fill for categorical/version data, and avoid blind imputation for timestamp/key fields.

## Non-Numeric Columns

- `WMAN.Tm` (DateTime): 12098 non-numeric values; examples: '2018-01-04 00:00:00', '2018-01-04 00:00:07', '2018-01-04 00:00:15'
- `WMAN.Plc.Version` (CHAR(100)): 12098 non-numeric values; examples: '1500_fr_v150806'
- `WMAN.InitFileVersion` (CHAR(100)): 12098 non-numeric values; examples: 'sinoma42.2_v20150728'
- `WMAN.Mirror.Version` (CHAR(100)): 12098 non-numeric values; examples: 'com_1500_standard_v1.2'
