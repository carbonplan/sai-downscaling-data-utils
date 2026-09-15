
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

# sai-downscaling-data-utils

This repository shares utilities for accessing and analyzing output from the [srm-downscaling project](https://carbonplan.github.io/srm-downscaling/). If you're new to the data, start with [`notebooks/quickstart.ipynb`](notebooks/quickstart.ipynb). It's a short example that loads data for one region and season and saves the result to a file. [`notebooks/subsetting-and-exporting.ipynb`](notebooks/subsetting-and-exporting.ipynb) goes through each of those steps in more detail.

To get started, we recommend following the steps below:

**01 — [Set up your environment](#installation)**
Install Git and Pixi, then clone the repository and install dependencies.

**02 — [Run the notebooks](#running-the-notebooks)**
Launch JupyterLab and open the notebooks to start working with the data.

## data

> [!IMPORTANT]
> Data associated with this repository are subject to additional [terms of data access](https://carbonplan.github.io/srm-downscaling/terms-of-data-access.html).

If you come across a term you don't know (e.g. *store*, *group* or *chunk*), check the [glossary](GLOSSARY.md). We use the same terms as the Zarr and Icechunk documentation.

## installation

All installation steps are run from a terminal. Once you have a terminal open, follow the steps below.

### use `Git` to download the access utilities

Verify Git is installed:

```bash
git --version
```

If not installed, follow the [installation instructions](https://git-scm.com/downloads).

Clone the repository:

```bash
git clone https://github.com/carbonplan/sai-downscaling-data-utils
cd sai-downscaling-data-utils
```

Cloning the repository will copy the access utilities here on Github to your computer to allow you to run them.

### use `Pixi` to ensure you have all the necessary packages

This project uses [Pixi](https://pixi.sh) for environment and dependency management. Using Pixi will ensure that you can import all of the packages required by the access utilities.

Verify Pixi is installed:

```bash
pixi --version
```

If not installed, follow the [installation instructions](https://pixi.sh/latest/#installation).

Install dependencies (a.k.a. the packages you need to run the access utilities):

```bash
pixi install
```

## running the notebooks

There are four notebooks in the `notebooks/` folder:

- [`quickstart.ipynb`](notebooks/quickstart.ipynb): a short example that loads data for one region and season and saves the result to a file. Start here.
- [`subsetting-and-exporting.ipynb`](notebooks/subsetting-and-exporting.ipynb): a longer walk-through of each step, with more options and example analysis code.
- [`compute-resources.ipynb`](notebooks/compute-resources.ipynb): tips for running a global analysis without running out of memory.
- [`input-data.ipynb`](notebooks/input-data.ipynb): a look at the GCM input data the downscaling started from (see [input data](#input-data)).

One way to run the notebooks is using JupyterLab. Starting JupyterLab via Pixi helps ensure all the required packages are available.

```bash
pixi run jupyter lab
```

Then open a notebook from the `notebooks/` folder. Most of the notebooks use helper functions from the [`scripts/`](scripts/README.md) folder, so open them from inside the cloned repository. The `subsetting-and-exporting.ipynb` notebook walks through:

- Loading the downscaled dataset from cloud storage
- Selecting a region of interest using a vector boundary (Natural Earth or your own file)
- Subsetting by scenario, GCM, ensemble member, downscaling method, and variable
- Reading and applying the published quality flags
- Accessing the data which has been bias-corrected but not downscaled (i.e. on the coarse GCM grid)
- Downloading to a local file


## downloading data from the command line

If you know the exact data you want and don't want to bother with an interactive session, `scripts/download.sh` is a
command-line counterpart to the notebook. It takes the same choices — scenario, GCM,
ensemble member, downscaling_method, region, variable, date range — as arguments, and downloads the corresponding subset 
to your local computer. You can download data in either `netCDF` or `Zarr` formats. Below we outline some helpful options
to pass to the script. Run `./scripts/download.sh --help` to see the full list of available options.

Every download needs you to say exactly which data you want: the model (`--gcm`, `CESM2-WACCM6` or `UKESM1-1-LL`), downscaling method (`--method`, `bcsd` or `qdmsd`), product (`--product`, `downscaled`, `debiased_coarse` or `input`), scenario, variable and ensemble member. If one of them is missing or isn't available, the script stops and lists the options you can choose from.

Check what a request costs before downloading anything by using the flag `--dry-run`:

```bash
./scripts/download.sh --scenario ssp245 --gcm CESM2-WACCM6 --method bcsd \
    --product downscaled --variable tas --member 003 \
    --start 2050-01-01 --end 2059-12-31 --bbox 68 6 98 38 --dry-run
```

Download a single-point time series:

```bash
./scripts/download.sh --scenario historical --gcm CESM2-WACCM6 --method bcsd \
    --product downscaled --variable tas --member r3i1p1f1 \
    --point 28.6 77.2 --start 1990-01-01 --end 1999-12-31 --output delhi.nc
```

Download a region as `NetCDF`:

```bash
./scripts/download.sh --scenario g6_1p5k --gcm CESM2-WACCM6 --method bcsd \
    --product downscaled --variable pr --member 003 \
    --bbox 68 6 98 38 --start 2050-01-01 --end 2059-12-31 \
    --output india_pr.nc
```

Download a region as `Zarr`:

```bash
./scripts/download.sh --scenario g6_1p5k --gcm CESM2-WACCM6 --method bcsd \
    --product downscaled --variable pr --member 003 \
    --bbox 68 6 98 38 --start 2050-01-01 --end 2059-12-31 \
    --format zarr --output india_pr.zarr
```

The ensemble members and variables available for each GCM differ. You can see what data are available with the `--list-members` flag:

```bash
./scripts/download.sh --scenario ssp245 --gcm CESM2-WACCM6 --method bcsd \
    --product downscaled --list-members
```

```
member       coverage                  variables
001          2015-01-01 to 2099-12-31  pr rsds tas
...
006          2015-01-01 to 2068-12-31  pr rsds tas tasmax tasmin
```

Then pick one with `--member`:

```bash
./scripts/download.sh --scenario ssp245 --gcm CESM2-WACCM6 --method bcsd \
    --product downscaled --variable tas --member 008 \
    --point 28.6 77.2 --start 2050-01-01 --end 2059-12-31
```

Download the bias-corrected data instead of the downscaled data with `--product debiased_coarse`. This coarse data is
at the GCM's resolution (about 1° for `CESM2-WACCM6`) as opposed to the 0.25° resolution of the downscaled data. The bias-corrected
data includes the diurnal temperature range (`dtr`) instead of `tasmin` since the daily minimum temperature is calculated as part of the
downscaling step.

```bash
./scripts/download.sh --scenario ssp245 --gcm CESM2-WACCM6 --method bcsd \
    --product debiased_coarse --variable dtr --member 008 \
    --point 28.6 77.2 --start 2050-01-01 --end 2059-12-31
```

Output files are named after the data they contain, so repeated downloads never
overwrite one another:

```
pt28.6N-77.2E_CESM2-WACCM6_bcsd_ssp245_003_tas_2050-2055.nc
bbox-68E-6N-98E-38N_CESM2-WACCM6_bcsd_ssp245_003_pr_2050-2059.nc
```

Coordinates are written with N/S and E/W instead of plus and minus signs, so a point at 40, -105 becomes `pt40N-105W`. Pass `--output` if you'd rather choose the name yourself.

Pass `--qa-flags` to write the published quality flags alongside the variable.

The download script offers additional guidance for users:

- **Validates dates against the member you asked for.** Coverage differs —
  `g6_1p5k` begins in 2035, `g6_1p5k_end` covers 2085–2100 and is published for
  `CESM2-WACCM6` only, and coverage varies *within* a scenario: on
  `CESM2-WACCM6`/`ssp245`, members `001`–`005` run to 2099 while `006`–`010`
  stop in 2069. The range is read from the member's own time axis, so asking
  outside it fails loudly instead of writing an empty file.
- **Warns before a large download.** Data is stored in spatiotemporal "chunks" which span about a year of time over a
  9°×18° tile, so a request touching a wide area reads far more than it returns.
  Any requests over 1 GB prompts for confirmation; pass `--yes` to skip the prompt,
  or `--dry-run` to see the estimate and stop.

## input data

We have made our pre-processed GCM input datasets available. The pre-processing included
steps to align with CMIP variable names and units, a proleptic
Gregorian calendar and longitudes from -180 to 180. These data
also include `hurs` (near-surface relative humidity), which the downscaled product does not.

[`notebooks/input-data.ipynb`](notebooks/input-data.ipynb) walks through them: what each
store holds, what a request costs, and what bias correction changed. The command-line
tool downloads subsets with `--product input`:

```bash
./scripts/download.sh --scenario ssp245 --gcm CESM2-WACCM6 --product input --list-members
./scripts/download.sh --scenario ssp245 --gcm CESM2-WACCM6 --product input \
    --variable tas --member 003 --point 28.6 77.2 --start 2050-01-01 --end 2059-12-31
```

The input stores currently live on CarbonPlan's `carbonplan-srm` S3 bucket (anonymous,
read-only) and will move to Source Cooperative. 

The input data storage structure differs from the downscaled product's. A chunk holds the whole globe
for 30 days (`CESM2-WACCM6`) or 60 days (`UKESM1-1-LL`), so accessing a region costs the same as a
single point, and a long point series is expensive since it must read in the entire dataset (e.g. 6.9 GB for 85 years of one
`CESM2-WACCM6` member). Maps are cheap.

## license

All the code in this repository is [MIT](https://choosealicense.com/licenses/mit/) licensed.

## about us

CarbonPlan is a non-profit organization that uses data and science for climate action. We aim to improve the transparency and scientific integrity of carbon removal and climate solutions through open data and tools. Find out more at [carbonplan.org](https://carbonplan.org/) or get in touch by [opening an issue](https://github.com/carbonplan/sai-downscaling-data-utils/issues/new) or [sending us an email](mailto:hello@carbonplan.org).
