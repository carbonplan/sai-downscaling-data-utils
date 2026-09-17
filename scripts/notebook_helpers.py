"""Helpers for notebooks/subsetting-and-exporting.ipynb and compute-resources.ipynb.

The notebook imports these so its cells can show the steps a reader adapts --
selections, plots, exports -- without long setup and reporting code in between.
Data access itself lives in data_access.py, which the command-line tool shares.
"""

from __future__ import annotations

import sys

import xarray as xr

from data_access import describe_request, ensemble_member, load_downscaling_store, qa_flag_vars

__all__ = [
    "check_dates",
    "first_decade",
    "request_size_examples",
    "subset_bbox",
    "subset_time",
    "summarize_quality_flags",
    "check_tasmin_reconstruction",
    "peak_memory_gb",
]


def check_dates(ds: xr.Dataset | xr.DataArray, start: str, end: str | None = None) -> None:
    """Stop with a clear message when dates are not in quotes or fall outside the data.

    Pass `start` and `end` for a date range, or only `start` for a single year
    ("2055"), month ("2055-07") or day ("2055-07-04").
    """
    for date in (start, end):
        if date is not None and not isinstance(date, str):
            raise TypeError(f'write dates as text in quotes, e.g. "2050-01-01" or "2050", not {date!r}')
    # A slice keeps the time dimension even when it selects a single day.
    if ds.sel(time=slice(start, end or start)).sizes["time"] == 0:
        first, last = str(ds.time.values[0])[:10], str(ds.time.values[-1])[:10]
        if end is None:
            raise ValueError(f"no data for {start}. This data covers {first} to {last}.")
        raise ValueError(
            f"no data for {start} to {end}. This data covers {first} to {last}, "
            "and the start date has to come before the end date."
        )


def first_decade(dataset: xr.Dataset | xr.DataArray) -> slice:
    """A 10-year window guaranteed to exist in whichever scenario is loaded.

    Scenario coverage differs (historical 1978-2014, ssp245 2015-2099,
    g6_1p5k 2035-2084, g6_1p5k_end 2085-2100), so a hard-coded date range
    would silently return an empty selection for some scenarios. Anchoring to
    the first available year keeps every example valid whichever scenario and
    GCM you picked.
    """
    year0 = int(str(dataset.time.values[0])[:4])
    return slice(f"{year0}-01-01", f"{year0 + 9}-12-31")


def subset_bbox(ds: xr.Dataset, lon_min: float, lon_max: float, lat_min: float, lat_max: float) -> xr.Dataset:
    """Select a lat/lon box, whether the coordinates run ascending or descending."""
    lat_slice = slice(lat_min, lat_max) if ds.lat[0] < ds.lat[-1] else slice(lat_max, lat_min)
    lon_slice = slice(lon_min, lon_max) if ds.lon[0] < ds.lon[-1] else slice(lon_max, lon_min)
    return ds.sel(lat=lat_slice, lon=lon_slice)


def subset_time(ds: xr.Dataset, start_date=None, end_date=None, months=None, seasons=None) -> xr.Dataset:
    """
    Flexible temporal subsetting of a dataset.

    Parameters
    ----------
    ds : xarray.Dataset
        Input dataset with time coordinate
    start_date : str, optional
        Start date in 'YYYY-MM-DD' format
    end_date : str, optional
        End date in 'YYYY-MM-DD' format
    months : list of int, optional
        List of months to select (1-12)
    seasons : list of str, optional
        List of seasons to select ('DJF', 'MAM', 'JJA', 'SON')

    Returns
    -------
    xarray.Dataset
        Temporally subsetted dataset
    """
    result = ds

    # Date range selection
    if start_date or end_date:
        result = result.sel(time=slice(start_date, end_date))

    # Month selection
    if months:
        result = result.sel(time=result.time.dt.month.isin(months))

    # Season selection
    if seasons:
        result = result.sel(time=result.time.dt.season.isin(seasons))

    return result


def request_size_examples(da: xr.DataArray) -> None:
    """Print what four typical requests read. Nothing is computed.

    A point's full record, a regional decade, a global decade and a single
    global day -- the rows of the cost table in Section 2 of the notebook.
    """
    decade = first_decade(da)  # scenario-safe; never an empty selection

    # 1. One point, whole record -- the pattern this store is built for
    describe_request(da.sel(lat=28.6, lon=77.2, method="nearest"), "Delhi point, full record")

    # 2. A region over a decade -- still very reasonable
    describe_request(da.sel(time=decade, lat=slice(6, 38), lon=slice(68, 98)), "India box, 10 yr")

    # 3. Global over a decade -- the kind of request that crashes notebooks if loaded all at once
    describe_request(da.sel(time=decade), "Global, 10 yr")

    # 4. A single global day -- 4 MB of numbers, tens of GB of reads
    describe_request(da.isel(time=0), "Global, single day")


def summarize_quality_flags(
    ds: xr.Dataset,
    variable: str,
    *,
    year: str,
    lat: slice,
    lon: slice,
    region: str = "India box",
) -> xr.Dataset | None:
    """Print how much of one year over a region the flags mark, and what masking does.

    `ds` must be loaded with ``qa_flags=True``. Masking keeps the pixel-days whose
    ``qa_flag_time_varying`` is 0 and sets the rest to NaN::

        ds[variable].where(ds["qa_flag_time_varying"] == 0)

    Returns the computed summary, or None when the group carries no per-day flag.
    """
    flags = qa_flag_vars(ds, variable)
    if "qa_flag_time_varying" not in flags:
        print(f"\n{variable} carries no per-day quality flag in this group. dtr, available")
        print("under debiased_coarse only, has no flags at all. Check qa_flag_vars(...)")
        print("rather than assuming a flag exists.")
        return None

    # One year over the region, to keep this in the same size bracket as the rest of
    # the notebook. Note the flag adds its own chunks to the request.
    check_dates(ds, year)
    region_qa = ds.sel(time=year, lat=lat, lon=lon)

    describe_request(region_qa[variable], f"{region}, {year}, data")
    describe_request(region_qa["qa_flag_time_varying"], f"{region}, {year}, flag")

    masked = region_qa[variable].where(region_qa["qa_flag_time_varying"] == 0)
    stats = {
        "flagged_days": (region_qa["qa_flag_time_varying"] == 1).mean(),
        "raw_mean": region_qa[variable].mean(),
        "masked_mean": masked.mean(),
    }
    # Groups differ in which time-invariant flags they carry, so only ask for
    # the ones present -- assuming both exist raises a KeyError on most members.
    invariant = [f for f in ("trend_distortion_flag", "qa_flag_time_invariant") if f in flags]
    for name in invariant:
        stats[name] = (region_qa[name] == 1).mean()

    # One graph, so the region and its flags are each read once.
    summary = xr.Dataset(stats).compute()

    units = ds[variable].attrs.get("units", "")
    print(f"\nflagged pixel-days       {float(summary['flagged_days']) * 100:7.4f}%")
    for name in invariant:
        print(f"{name:24s} {float(summary[name]) * 100:7.4f}% of pixels")
    absent = [f for f in ("trend_distortion_flag", "qa_flag_time_invariant") if f not in flags]
    if absent:
        print(f"{'not in this group':24s} {', '.join(absent)}")
    print(f"regional mean, raw       {float(summary['raw_mean']):7.3f} {units}")
    print(f"regional mean, masked    {float(summary['masked_mean']):7.3f} {units}")
    if float(summary["flagged_days"]) == 0:
        print("\nNothing was flagged in this selection, so the two means are identical.")
        print("That is the flag doing its job, not the mask failing to apply -- other")
        print("regions, variables and members will not all come back clean.")
    else:
        print("\nThe gap between the two means is what the flagged pixel-days were")
        print("contributing. Decide deliberately whether to keep them.")
    print("\nMasking sets flagged pixel-days to NaN. Reductions such as .mean() skip")
    print("NaN by default, and .weighted() renormalizes across it, so a masked mean")
    print("stays correct rather than being dragged toward zero.")
    return summary


def check_tasmin_reconstruction(
    scenario: str,
    *,
    gcm: str,
    method: str,
    member: str,
    year: str,
    lat: slice,
    lon: slice,
    region: str = "India box",
) -> xr.Dataset:
    """Check that ``tasmin == tasmax - dtr`` on the coarse grid, and print the result.

    `member` must contain ``dtr``, which comes from the same members as
    tasmax/tasmin (members_for(...) lists them). The same member is used for all three.
    """
    dtr_member = ensemble_member(scenario, "dtr", gcm, method, member, product="debiased_coarse")
    pieces = {}
    for name in ("tasmax", "tasmin", "dtr"):
        da = load_downscaling_store(
            scenario, name, gcm=gcm, method=method, member=dtr_member, product="debiased_coarse",
        )[name]
        check_dates(da, year)
        pieces[name] = da.sel(time=year, lat=lat, lon=lon)

    residual = pieces["tasmin"] - (pieces["tasmax"] - pieces["dtr"])
    check = xr.Dataset(
        {
            "largest_residual": abs(residual).max(),
            "dtr_min": pieces["dtr"].min(),
            "dtr_max": pieces["dtr"].max(),
        }
    ).compute()

    print(f"{gcm}/{method}/debiased_coarse/{scenario}, member {dtr_member}, {region}, {year}")
    print(f"  largest |tasmin - (tasmax - dtr)|  {float(check['largest_residual']):.3g} K")
    print(f"  dtr range                          {float(check['dtr_min']):.2f} to {float(check['dtr_max']):.2f} K")
    return check


def peak_memory_gb() -> float | None:
    """The most memory this Python process has used so far, in GB, or None on Windows."""
    try:
        import resource
    except ImportError:  # Windows has no resource module
        return None
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes, Linux kilobytes.
    return peak / 1024**3 if sys.platform == "darwin" else peak / 1024**2
