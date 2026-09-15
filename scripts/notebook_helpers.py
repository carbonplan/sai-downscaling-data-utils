"""Helpers for notebooks/subsetting-and-exporting.ipynb.

The notebook imports these so its cells can show the steps a reader adapts --
selections, plots, exports -- without long setup and reporting code in between.
Data access itself lives in data_access.py, which the command-line tool shares.
"""

from __future__ import annotations

import copy

import xarray as xr

from data_access import describe_request, ensemble_member, load_downscaling_store, qa_flag_vars

__all__ = [
    "DEMO_DATES",
    "demo_dates",
    "first_decade",
    "request_size_examples",
    "subset_bbox",
    "subset_time",
    "summarize_quality_flags",
    "check_tasmin_reconstruction",
]

# Example dates for each scenario, chosen to fall inside its coverage (see the table in
# Section 2 of the notebook). Sections 4 and 6 read from these, so they stay valid
# whichever scenario is picked.
DEMO_DATES = {
    "historical": {  # 1978-2014
        "decade_start": "1990-01-01",
        "decade_end": "1999-12-31",
        "single_year": "1995",
        "baseline_start": "1980-01-01",
        "baseline_end": "2000-12-31",
        "export_start": "1990-01-01",
        "export_end": "1995-12-31",
    },
    "ssp245": {  # 2015-2099 on members 001-005; 006-010 stop in 2069
        "decade_start": "2050-01-01",
        "decade_end": "2059-12-31",
        "single_year": "2055",
        "baseline_start": "2030-01-01",
        "baseline_end": "2050-12-31",
        "export_start": "2050-01-01",
        "export_end": "2055-12-31",
    },
    "g6_1p5k_end": {  # 2085-2100, CESM2-WACCM6 only -- continues g6_1p5k
        "decade_start": "2085-01-01",
        "decade_end": "2094-12-31",
        "single_year": "2090",
        "baseline_start": "2085-01-01",
        "baseline_end": "2095-12-31",
        "export_start": "2090-01-01",
        "export_end": "2095-12-31",
    },
    "g6_1p5k": {  # 2035-2084 -- note the late start
        "decade_start": "2050-01-01",
        "decade_end": "2059-12-31",
        "single_year": "2055",
        "baseline_start": "2035-01-01",
        "baseline_end": "2055-12-31",
        "export_start": "2050-01-01",
        "export_end": "2055-12-31",
    },
}


def demo_dates(scenario: str) -> dict[str, str]:
    """Example date ranges that fall inside `scenario`'s coverage."""
    if scenario not in DEMO_DATES:
        raise ValueError(f"no demo dates for scenario {scenario!r}; one of {sorted(DEMO_DATES)}")
    return copy.deepcopy(DEMO_DATES[scenario])


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
    year: str,
    lat: slice,
    lon: slice,
    region: str = "India box",
) -> xr.Dataset:
    """Check that ``tasmin == tasmax - dtr`` on the coarse grid, and print the result.

    ``dtr`` comes from the same members as tasmax/tasmin, so its default member
    is used for all three.
    """
    dtr_member = ensemble_member(scenario, "dtr", gcm, method, product="debiased_coarse")
    pieces = {
        name: load_downscaling_store(
            scenario, name, gcm=gcm, method=method, member=dtr_member, product="debiased_coarse",
        )[name].sel(time=year, lat=lat, lon=lon)
        for name in ("tasmax", "tasmin", "dtr")
    }

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
