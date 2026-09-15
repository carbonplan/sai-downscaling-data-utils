# scripts

This folder holds the command-line download tool and the Python modules that it and the notebooks import. To download data, see [downloading data from the command line](../README.md#downloading-data-from-the-command-line) in the main README; terms such as _store_, _group_ and _ensemble member_ are defined in the [glossary](../GLOSSARY.md).

| File | What it is | Used by |
|---|---|---|
| [`download.sh`](download.sh) | Command-line entry point. Runs `download.py` inside the Pixi environment. | You, from a terminal |
| [`download.py`](download.py) | The download tool: checks a request against the data, estimates its size and writes NetCDF or Zarr. | `download.sh`, or `pixi run python scripts/download.py` |
| [`srm_access.py`](srm_access.py) | Reading the downscaled and bias-corrected data: which store to open, which members and variables a scenario contains, coverage, loading a group, request sizes and output filenames. | `download.py`, `input_access.py` and [`subsetting-and-exporting.ipynb`](../notebooks/subsetting-and-exporting.ipynb) |
| [`notebook_helpers.py`](notebook_helpers.py) | Longer example code moved out of the subsetting notebook: example dates for each scenario, request-size examples, the quality-flag summary and the `dtr` check, plus `first_decade`, `subset_bbox` and `subset_time`. | [`subsetting-and-exporting.ipynb`](../notebooks/subsetting-and-exporting.ipynb) |
| [`input_access.py`](input_access.py) | Reading the input data: the harmonized GCM output the downscaling pipeline starts from. | `download.py --product input` |

## Changing a helper

The subsetting notebook imports its helper functions from `srm_access.py` and `notebook_helpers.py`, so a change made in the module reaches the notebook after a kernel restart. The exception is [`input-data.ipynb`](../notebooks/input-data.ipynb), which carries its own copy of `input_access.py` so it can run on its own; a change to either one needs the same change in the other.
