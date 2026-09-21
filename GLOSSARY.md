# Glossary

The terms below appear in the [notebooks](notebooks/), the command-line tool and the [README](README.md). Storage terms follow the [Zarr specification](https://zarr-specs.readthedocs.io/en/latest/v3/core/index.html), which the [Icechunk documentation](https://icechunk.io/en/stable/) builds on, so they carry the same meaning in both.

**Sections:** [Storage and data format](#storage-and-data-format) · [Requests and computation](#requests-and-computation) · [Climate data](#climate-data) · [Input data](#input-data)

## Storage and data format

### Array

A block of values with named dimensions and a fixed shape, such as `tas` on `(time, lat, lon)`. Arrays sit inside groups.

### Attributes

Descriptive information stored alongside the values, such as units, long names and processing details. Xarray lists them under `Attributes` when a dataset is displayed.

### Chunk

One regularly shaped piece of an array, and the smallest unit that can be read: reading any value in a chunk reads the whole chunk. A downscaled chunk covers 365 days over a 9° × 18° tile (3.8 MB); an input chunk covers the whole globe for 30 days (`CESM2-WACCM6`) or 60 days (`UKESM1-1-LL`).

### Group

A named container inside a store that holds arrays and other groups, as a folder holds files and subfolders. In the published stores each combination of method, scenario, variable and member is one group, for example `bcsd/ssp245/tas/003`.

### Icechunk

An open-source storage engine for Zarr. The published data and the input data are both Icechunk stores.

### NetCDF

A widely used single-file format for gridded climate data (`.nc`). The notebooks and the command-line tool both export to it.

### S3

Amazon's cloud object storage. The published stores and the input stores all sit in a public S3 bucket hosted by [Source Cooperative](https://source.coop), readable without an account.

### Shard

One stored object that bundles several chunks, so a store holds fewer, larger objects. Chunks inside a shard are still read individually, so a request reads the same chunks either way. An input shard spans 480 days (`CESM2-WACCM6`) or 960 days (`UKESM1-1-LL`), which sets how precisely the input notebook lists coverage without reading data.

### Store

The container for every group and array in one Zarr tree, together with their metadata; it takes the place a file has in formats like NetCDF. There is one published store per GCM, `CESM2-WACCM6-ERA5-global` and `UKESM1-1-LL-ERA5-global`, and one input store per GCM.

### Tree

The nesting of groups inside a store, called a *hierarchy* in the Zarr specification. The published stores run `{method}/{scenario}/{variable}/{member}`, with `debiased_coarse/` after the method for the bias-corrected product; the input stores have one group per scenario.

### Zarr

A cloud-optimized format for multidimensional arrays that stores data as many chunks rather than as one file. The stores use Zarr version 3.

## Requests and computation

### Area weighting

Weighting each grid cell by its true area so a spatial mean is not skewed toward the poles. On a regular latitude–longitude grid the weight is proportional to `cos(lat)`.

### CRS

Coordinate reference system: the definition that ties `lat`/`lon` values to places on Earth. The data uses `EPSG:4326`, latitude and longitude on the WGS 84 datum.

### Dask

A Python library that splits large arrays into pieces and processes them in parallel. Xarray uses it for every dataset the notebooks open.

### Data read

The decompressed size of every chunk a request touches, in full. It is usually larger than the logical size.

### Dataset

An Xarray object holding one or more arrays that share coordinates such as `time`, `lat` and `lon`. In the subsetting notebook, `ds`, `ds_clipped` and `ds_export` are datasets.

### Lazy

Describes an operation that is recorded but not yet run. Values are read only when needed, for example by `.load()`, `.compute()`, plotting or writing a file.

### Load

Reading the values of a lazy result into memory (RAM). Loading needs enough memory to hold the whole result.

### Logical size

The in-memory size of the values a request returns. `describe_request(...)` reports it alongside the data read.

### Mask, clip

Masking sets values outside a shape, such as a country border, to NaN. Clipping also trims the grid to the shape's bounding box.

### NaN

"Not a Number": the placeholder for a missing value. It marks grid cells outside a clipped region and, in the input stores, days a member does not cover.

### Request

A selection asked of a store: a variable, a place and a date range. Its cost is set by the chunks it touches, not by the number of values it returns; `describe_request(...)` and `./scripts/download.sh --dry-run` estimate it before any data is read.

### Resample

Changing the time step of a dataset by aggregating, for example daily values to annual means. In Xarray this is `resample(time=...)`.

## Climate data

### Bias correction

Adjusting GCM output so its statistics match observation-based data (ERA5 reanalysis, 1978–2014) on the GCM's grid. Also called *debiasing*.

### Coverage

The first and last dates held for a given scenario, variable and member. Members of the same scenario can differ.

### Downscaling

Turning coarse GCM output into a finer grid, 0.25° here, using observation-based data. It has 2 steps: bias correction, then spatial disaggregation.

### Ensemble member

One run of a GCM under a scenario, named by an ID such as `003` or `r2i1p1f2`. Members start from slightly different conditions, so together they sample natural climate variability. Also called a *realization*.

### GCM

Global climate model: a simulation of the whole Earth system on a coarse grid. The data covers `CESM2-WACCM6` and `UKESM1-1-LL`.

### Grid cell

One latitude–longitude box of a grid, also called a pixel. Downscaled grid cells are 0.25° on a side.

### Method

The downscaling approach. `bcsd` bias-corrects with nonparametric quantile mapping and `qdmsd` with quantile delta mapping; both then apply spatial disaggregation.

### Native grid

A GCM's own grid, also called the coarse grid: 0.94° × 1.25° for `CESM2-WACCM6` and 1.25° × 1.875° for `UKESM1-1-LL`. The input data and the bias-corrected product use it.

### Product

The pipeline stage a published dataset comes from. `downscaled` is the final 0.25° data; `debiased_coarse` is the bias-corrected data on the native grid, before spatial disaggregation.

### Quality flag

An array of 0s and 1s stored beside the data, where 1 marks a grid cell, or a day at a grid cell, with a known issue. Every published group except `dtr` carries them.

### SAI

Stratospheric aerosol injection: a proposed form of solar radiation modification (SRM) that adds reflective particles to the stratosphere to cool the planet. The `g6_1p5k` scenarios simulate it.

### Scenario

The conditions a model run follows. `historical` is driven by past forcings (1978–2014 in the published data). `ssp245` follows SSP2-4.5, an intermediate emissions pathway. `g6_1p5k` follows the GeoMIP G6-1.5K-SAI experiment: SSP2-4.5 plus SAI from 2035, aimed at holding warming near 1.5 °C above preindustrial. `g6_1p5k_end` continues it to 2100 (`CESM2-WACCM6` only).

### Spatial disaggregation

Distributing bias-corrected coarse values onto the 0.25° grid using fine-scale patterns from observation-based data. The adjustment depends on the variable, for example additive for temperature and multiplicative for precipitation.

### Variable

A physical quantity. `tas`: daily mean 2 m air temperature (K). `tasmax`, `tasmin`: daily maximum and minimum 2 m air temperature (K). `pr`: precipitation rate (kg m-2 s-1). `rsds`: downward shortwave radiation at the surface (W m-2). `dtr`: diurnal temperature range, `tasmax` − `tasmin` (K; bias-corrected product only). `hurs`: near-surface relative humidity (input data only).

## Input data

### Harmonized

Prepared so both GCMs share conventions: CMIP variable names and units, a proleptic Gregorian calendar and longitudes from -180 to 180. Apart from that, harmonized input keeps each GCM's own values.

### Input store

One Icechunk store per GCM holding the GCM daily output the downscaling pipeline starts from, harmonized but before any bias correction, on the native grid. Each has one group per scenario, with every variable on `(ensemble_member, time, lat, lon)`.

### Manifest

The index an Icechunk store keeps of which chunks are stored and where. Listing it shows which members and years hold data without reading any values.
