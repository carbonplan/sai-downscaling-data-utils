
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

We built these utilities to access and analyze output from the [SAI Downscaling project](https://github.com/carbonplan/sai-downscaling). If you're new to the data, start with [`notebooks/quickstart.ipynb`](notebooks/quickstart.ipynb). It's a short example that loads data for one region and season and saves the result to a file. [`notebooks/subsetting-and-exporting.ipynb`](notebooks/subsetting-and-exporting.ipynb) goes through each of those steps in more detail.

To get started, work through the 2 steps below. They take you from a fresh machine to a
running notebook.

**01: [Set up your environment](#installation)**
Install Git and Pixi, then clone the repository and install dependencies.

**02: [Run the notebooks](#running-the-notebooks)**
Launch JupyterLab and open the notebooks to start working with the data.

## data

> [!IMPORTANT]
> Data accessed with these utilities are subject to the [Terms of Data Access](TERMS_OF_DATA_ACCESS). The download tool writes a copy of them alongside every export.

If you come across a term you don't know (e.g. *store*, *group* or *chunk*), check the [glossary](GLOSSARY.md). We use the same terms as the Zarr and Icechunk documentation.

## installation

You run every installation step from a terminal. Open one, then work through the steps below.

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

Cloning copies the access utilities from GitHub onto your computer so you can run them. You only
need to do this once.

### use `Pixi` to ensure you have all the necessary packages

We use [Pixi](https://pixi.sh) for environment and dependency management. It makes sure every
package the access utilities import is present and at the version we tested against.

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

We ship 4 notebooks in the `notebooks/` folder. Which one you want depends on how much detail
you need:

- [`quickstart.ipynb`](notebooks/quickstart.ipynb): a short example that loads data for one region and season and saves the result to a file. Start here.
- [`subsetting-and-exporting.ipynb`](notebooks/subsetting-and-exporting.ipynb): a longer walk-through of each step, with more options and example analysis code.
- [`compute-resources.ipynb`](notebooks/compute-resources.ipynb): tips for running a global analysis on a laptop, an HPC system or a cloud machine without running out of memory.
- [`input-data.ipynb`](notebooks/input-data.ipynb): a look at the GCM input data the downscaling started from (see [input data](#input-data)).

We run the notebooks in JupyterLab. Starting it through Pixi makes sure every required package is
available.

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

Use `pixi run download` when you want a file without opening a notebook. Run it from the
cloned repository after [installation](#installation). It reads the public data without an
account and saves a subset as NetCDF by default. The command works on Windows, macOS and Linux.

You choose a model (`--gcm`), scenario, product, variable and ensemble member. For the
downscaled and bias-corrected products, you also choose a downscaling method (`--method`).
If a choice is missing or unavailable, the command tells you what to choose instead.

### make your first download

First, list the members for the data you want. The list shows each member's dates and variables:

```text
pixi run download --scenario ssp245 --gcm CESM2-WACCM6 --method bcsd --product downscaled --list-members
```

For example, member `008` contains `tas` (air temperature) for 2050–2059. Check how much
data a Delhi point request would read before downloading it:

```text
pixi run download --scenario ssp245 --gcm CESM2-WACCM6 --method bcsd --product downscaled --variable tas --member 008 --point 28.6 77.2 --start 2050-01-01 --end 2059-12-31 --dry-run
```

`--point` takes latitude, then longitude. The dry run reports the estimated data read and
downloads nothing. To save that selection, replace `--dry-run` with `--output delhi_tas.nc`:

```text
pixi run download --scenario ssp245 --gcm CESM2-WACCM6 --method bcsd --product downscaled --variable tas --member 008 --point 28.6 77.2 --start 2050-01-01 --end 2059-12-31 --output delhi_tas.nc
```

The commands are on single lines so they also work in PowerShell and Command Prompt.
Run `pixi run download --help` for the full list of options.

### other options

- Use `--bbox LON_MIN LAT_MIN LON_MAX LAT_MAX` to download a region instead of a point.
  For example, `--bbox 68 6 98 38` selects a region around India. A regional request
  may read much more data than a point request.
- Use `--format zarr --output delhi_tas.zarr` to save Zarr instead of NetCDF. Choose an
  output name ending in `.zarr` for Zarr or `.nc` for NetCDF.
- Use `--product debiased_coarse` for bias-corrected data on the GCM's grid, before
  downscaling. This product has `dtr` (diurnal temperature range) in place of `tasmin`.
  For the pre-processed GCM data, see [input data](#input-data); `--product input` does
  not take `--method`.
- Use `--qa-flags` with the downscaled or bias-corrected product to include the
  published quality flags. A value of 1 marks a grid cell, or a day at a grid
  cell, with a known issue.

The tool checks your dates against the chosen member's actual coverage. Coverage can vary
even within a scenario, so use `--list-members` before choosing dates. A request that reads
more than 1 GB prompts you before downloading; `--yes` skips that prompt. A wide request
can read substantially more data than the resulting file contains because the stored data
are read in chunks.

Without `--output`, the tool builds a name from your selection, including the location,
model, scenario, member, variable and years. Repeating the same request can replace the
existing file, so choose a different output path if you want to keep both copies.

## input data

We have made our pre-processed GCM input datasets available. The pre-processing included
steps to align with CMIP variable names and units, a proleptic
Gregorian calendar and longitudes from -180 to 180. These data
also include `hurs` (near-surface relative humidity), which the downscaled product does not.

[`notebooks/input-data.ipynb`](notebooks/input-data.ipynb) walks through them: what each
store holds, how much data a request reads, and what bias correction changed. To download a
subset from the command line, choose `--product input`. There is no `--method` because these
data have not been downscaled. First, list the available members:

```text
pixi run download --scenario ssp245 --gcm CESM2-WACCM6 --product input --list-members
```

Then check how much a point time series would read:

```text
pixi run download --scenario ssp245 --gcm CESM2-WACCM6 --product input --variable tas --member 003 --point 28.6 77.2 --start 2050-01-01 --end 2059-12-31 --dry-run
```

If you're ready to download it, run:

```text
pixi run download --scenario ssp245 --gcm CESM2-WACCM6 --product input --variable tas --member 003 --point 28.6 77.2 --start 2050-01-01 --end 2059-12-31 --output delhi_input_tas.nc
```

We keep the input stores on Source Cooperative in the same bucket as the downscaled and
bias-corrected output, under an `input/` prefix. You read them the same way as the rest:
anonymous and read-only.

The input data storage structure differs from the downscaled product's. A chunk holds the whole globe
for 30 days (`CESM2-WACCM6`) or 60 days (`UKESM1-1-LL`), so accessing a region reads as much as a
single point, and a long point series is slow since it must read in the entire dataset (e.g. 6.9 GB for 85 years of one
`CESM2-WACCM6` member). Maps are quick.

## license

All the code in this repository is [MIT](https://choosealicense.com/licenses/mit/) licensed. See the [licenses](https://sai-downscaling.readthedocs.io/en/latest/access-data/licenses.html) section of our documentation for details about the licenses for all of the input and output datasets.

## about us

CarbonPlan is a non-profit organization that uses data and science for climate action. We aim to improve the transparency and scientific integrity of carbon removal and climate solutions through open data and tools. Find out more at [carbonplan.org](https://carbonplan.org/) or get in touch by [opening an issue](https://github.com/carbonplan/sai-downscaling-data-utils/issues/new) or [sending us an email](mailto:hello@carbonplan.org).
