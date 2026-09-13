
<p align='left'>
  <a href='https://carbonplan.org/#gh-light-mode-only'>
    <img
      src='https://carbonplan-assets.s3.amazonaws.com/monogram/dark-small.png'
      height='48px'
    />
  </a>
  <a href='https://carbonplan.org/#gh-dark-mode-only'>
    <img
      src='https://carbonplan-assets.s3.amazonaws.com/monogram/light-small.png'
      height='48px'
    />
  </a>
</p>

# srm-downscaling-data-utils

This repository shares utilities for accessing and analyzing output from the [srm-downscaling project](https://carbonplan.github.io/srm-downscaling/). You'll probably be primarily interested in [`notebooks/subsetting-and-exporting.ipynb`](notebooks/subsetting-and-exporting.ipynb), which provides tools for accessing, subsetting, transforming, and exporting the downscaled data from the cloud to your local environment.

To get started, we recommend following the steps below:

**01 — [Set up your environment](#installation)**
Install Git and Pixi, then clone the repository and install dependencies.

**02 — [Run the notebook](#running-the-notebook)**
Launch JupyterLab and open the notebook to start working with the data.

## data

> [!IMPORTANT]
> Data associated with this repository are subject to additional [terms of data access](https://carbonplan.github.io/srm-downscaling/terms-of-data-access.html).

## installation

All installation steps are run from a terminal. Once you have a terminal open, follow the steps below.

### git

1. Verify Git is installed:

```bash
git --version
```

If not installed, follow the [installation instructions](https://git-scm.com/downloads).

1. Clone the repository:

```bash
git clone https://github.com/carbonplan/srm-downscaling-data-utils
cd srm-downscaling-data-utils
```

### pixi

This project uses [Pixi](https://pixi.sh) for environment and dependency management.

1. Verify Pixi is installed:

```bash
pixi --version
```

If not installed, follow the [installation instructions](https://pixi.sh/latest/#installation).

1. Install dependencies:

```bash
pixi install
```

## running the notebook

The `notebooks/subsetting-and-exporting.ipynb` notebook demonstrates how to subset and export the downscaled SRM data for a region of interest.

Launch JupyterLab with:

```bash
pixi run jupyter lab
```

Then open `notebooks/subsetting-and-exporting.ipynb`. The notebook walks through:

- Loading the dataset from cloud storage
- Selecting a region of interest using a vector boundary (Natural Earth or your own file)
- Subsetting by scenario, GCM, variable and ensemble member
- Reading and applying the published quality flags
- Exporting to a local file

To execute the notebook non-interactively (e.g. for testing):

```bash
pixi run jupyter nbconvert --to notebook --execute --inplace notebooks/subsetting-and-exporting.ipynb
```

## downloading from the command line

If you want a file rather than an interactive session, `scripts/download.sh` is a
command-line counterpart to the notebook. It takes the same choices — scenario,
variable, ensemble member, region, date range — as arguments.

Check what a request costs before downloading anything:

```bash
./scripts/download.sh --scenario ssp245 --start 2050-01-01 --end 2059-12-31 \
    --bbox 68 6 98 38 --dry-run
```

Download a single-point time series:

```bash
./scripts/download.sh --scenario historical --variable tas \
    --point 28.6 77.2 --start 1990-01-01 --end 1999-12-31 --output delhi.nc
```

Download a region as Zarr:

```bash
./scripts/download.sh --scenario g6_1p5k --variable pr \
    --bbox 68 6 98 38 --start 2050-01-01 --end 2059-12-31 \
    --format zarr --output india_pr.zarr
```

See what a scenario publishes before choosing:

```bash
./scripts/download.sh --scenario ssp245 --list-members
```

```
member       coverage                  variables
001          2015-01-01 to 2099-12-31  pr rsds tas
...
006          2015-01-01 to 2068-12-31  pr rsds tas tasmax tasmin
```

Then pick one with `--member`:

```bash
./scripts/download.sh --scenario ssp245 --variable tas --member 008 \
    --point 28.6 77.2 --start 2050-01-01 --end 2059-12-31
```

See `./scripts/download.sh --help` for the full list of options.

Output files are named after the data they contain, so repeated downloads never
overwrite one another:

```
pt28.6-77.2_CESM2-WACCM6_bcsd_ssp245_003_tas_2050-2055.nc
```

Pass `--output` to choose a name yourself.

Choose the model and downscaling method with `--gcm` (`CESM2-WACCM6` or
`UKESM1-1-LL`) and `--method` (`bcsd` or `qdmsd`); both default to
`CESM2-WACCM6` / `bcsd`. Omitting `--member` takes a pinned default per
scenario, which reproduces what releases before `v1.0.0` published.

Pass `--qa-flags` to write the published quality flags alongside the variable.
They share the data's chunk grid, so this roughly doubles the bytes read.

Two things it does for you:

- **Validates dates against the member you asked for.** Coverage differs —
  `g6_1p5k` begins in 2035, `g6_1p5k_end` covers 2085–2100 and is published for
  `CESM2-WACCM6` only, and coverage varies *within* a scenario: on
  `CESM2-WACCM6`/`ssp245`, members `001`–`005` run to 2099 while `006`–`010`
  stop in 2069. The range is read from the member's own time axis, so asking
  outside it fails loudly instead of writing an empty file.
- **Warns before a large download.** Chunks span about a year of time over a
  9°×18° tile, so a request touching a wide area reads far more than it returns.
  Anything over 5 GB prompts for confirmation; pass `--yes` to skip the prompt,
  or `--dry-run` to see the estimate and stop.

## license

All the code in this repository is [MIT](https://choosealicense.com/licenses/mit/) licensed.

## about us

CarbonPlan is a non-profit organization that uses data and science for climate action. We aim to improve the transparency and scientific integrity of carbon removal and climate solutions through open data and tools. Find out more at [carbonplan.org](https://carbonplan.org/) or get in touch by [opening an issue](https://github.com/carbonplan/srm-downscaling-data-utils/issues/new) or [sending us an email](mailto:hello@carbonplan.org).
