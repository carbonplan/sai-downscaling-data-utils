# scripts

This folder has the command-line download tool and the Python code that the tool and the notebooks share. To download data, see [downloading data from the command line](../README.md#downloading-data-from-the-command-line) in the main README. If you come across a term you don't know, check the [glossary](../GLOSSARY.md).

| File | What it does | Used by |
| --- | --- | --- |
| [`download.sh`](download.sh) | Runs `download.py` inside the Pixi environment. This is the one you call from a terminal. | You |
| [`download.py`](download.py) | The download tool. It checks your request, estimates how much data it will read and saves the result as NetCDF or Zarr. | `download.sh` |
| [`data_access.py`](data_access.py) | Opens the downscaled and bias-corrected data. It finds the right store, lists the members and variables a scenario contains, checks coverage, estimates request sizes and names output files. | `download.py`, `input_access.py` and the [quickstart](../notebooks/quickstart.ipynb), [subsetting-and-exporting](../notebooks/subsetting-and-exporting.ipynb) and [compute-resources](../notebooks/compute-resources.ipynb) notebooks |
| [`notebook_helpers.py`](notebook_helpers.py) | Longer pieces of example code that used to live in the notebooks, e.g. the quality flag summary, plus a check that your dates are inside the data. | The [subsetting-and-exporting](../notebooks/subsetting-and-exporting.ipynb) and [compute-resources](../notebooks/compute-resources.ipynb) notebooks |
| [`input_access.py`](input_access.py) | Opens the GCM input data the downscaling started from. | `download.py --product input` |

## changing a helper

If you change a function in `data_access.py` or `notebook_helpers.py`, restart the notebook's kernel to pick up the change. The one exception is [`input-data.ipynb`](../notebooks/input-data.ipynb), which keeps its own copy of the code in `input_access.py` so that it can run on its own. If you change one, make the same change in the other.
