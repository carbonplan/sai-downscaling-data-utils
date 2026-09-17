"""Shared access helpers for the CarbonPlan SRM downscaling dataset.

This module is the one place that knows which store to open, the group layout,
and which ensemble members each scenario contains.

Each store publishes two products, as zarr groups::

    {method}/{scenario}/{variable}/{member}                   # downscaled, 0.25 degree
    {method}/debiased_coarse/{scenario}/{variable}/{member}   # bias-corrected, native GCM grid

``downscaled`` is the finished product.
``debiased_coarse`` is the same GCM data after quantile-mapping bias
correction but *before* spatial disaggregation, left on the model's own grid
(about 1-2 degrees). It separates what bias correction did from what
downscaling did, and it is method-specific: bcsd and qdmsd correct biases
differently. It also carries ``dtr``, the diurnal temperature range, which the
pipeline bias-corrects only in order to reconstruct tasmin.

**Nothing about either tree is transcribed here.** The published store is the
authority. Opening a store fetches one manifest that lists every group, so
walking the whole hierarchy costs milliseconds, and ``layout()`` reads the
tree rather than keeping a hand-maintained table.
"""

from __future__ import annotations

import copy
import functools

import numpy as np
import xarray as xr

__all__ = [
    "BUCKET",
    "REGION",
    "STORE_BRANCH",
    "GCMS",
    "PRODUCTS",
    "METHODS",
    "VARIABLES",
    "COARSE_ONLY_VARIABLES",
    "layout",
    "scenarios_for",
    "variables_for",
    "members_for",
    "coverage",
    "ensemble_member",
    "check_members",
    "qa_flag_vars",
    "load_downscaling_store",
    "describe_request",
    "output_filename",
    "point_tag",
    "bbox_tag",
]

BUCKET = "us-west-2.opendata.source.coop"
REGION = "us-west-2"
_PREFIX = "carbonplan/srm-downscaling/output/production"

STORE_BRANCH = "v1.0.0"

# One store per GCM.
_STORES = {
    "CESM2-WACCM6": "CESM2-WACCM6-ERA5-global",
    "UKESM1-1-LL": "UKESM1-1-LL-ERA5-global",
}
GCMS = list(_STORES)

# The products each store publishes, and the group segment that selects one.
PRODUCTS = ["downscaled", "debiased_coarse"]
_PRODUCT_SEGMENT = {"downscaled": None, "debiased_coarse": "debiased_coarse"}

# The advertised sets, kept as literals so `--help` and error messages do not
# have to touch the network. What a *given* combination actually publishes
# comes from the store: see variables_for() and members_for().
METHODS = ["bcsd", "qdmsd"]
VARIABLES = ["tas", "tasmax", "tasmin", "pr", "rsds"]

# Published under debiased_coarse only; the name mirrors upstream's own
# COARSE_ONLY_VARIABLES. A disaggregated dtr would stop equalling
# tasmax - tasmin once the fine pair is reconciled, so upstream never writes it
# at 0.25 degrees. Use tasmax - tasmin there instead.
COARSE_ONLY_VARIABLES = ["dtr"]

# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


@functools.cache
def _open_root(gcm: str):
    """Open a store's root group. Cached: one manifest fetch per GCM."""
    import icechunk
    import zarr

    storage = icechunk.s3_storage(
        bucket=BUCKET,
        prefix=f"{_PREFIX}/{_STORES[gcm]}.icechunk",
        anonymous=True,
        region=REGION,
    )
    session = icechunk.Repository.open(storage).readonly_session(branch=STORE_BRANCH)
    return session, zarr.open_group(session.store, mode="r", zarr_format=3)


@functools.cache
def _layout(gcm: str, product: str) -> dict:
    _, root = _open_root(gcm)
    segment = _PRODUCT_SEGMENT[product]
    product_segments = {s for s in _PRODUCT_SEGMENT.values() if s}
    tree = {}
    for method in sorted(root.group_keys()):
        base = root[method]
        if segment is not None:
            if segment not in list(base.group_keys()):
                continue
            base = base[segment]
        tree[method] = {
            scenario: {
                variable: sorted(base[f"{scenario}/{variable}"].group_keys())
                for variable in sorted(base[scenario].group_keys())
            }
            for scenario in sorted(base.group_keys())
            if scenario not in product_segments
        }
    return tree


def _check_gcm(gcm: str) -> None:
    if gcm not in _STORES:
        raise ValueError(f"gcm must be one of {GCMS}, got {gcm!r}")


def _check_product(product: str) -> None:
    if product not in _PRODUCT_SEGMENT:
        raise ValueError(f"product must be one of {PRODUCTS}, got {product!r}")


def _where(gcm: str, method: str, product: str, *rest: str) -> str:
    """A readable address for error messages, naming the product only when not default."""
    segment = _PRODUCT_SEGMENT[product]
    return "/".join(p for p in (gcm, method, segment, *rest) if p)


def _group_path(method: str, scenario: str, variable: str, member: str, product: str) -> str:
    segment = _PRODUCT_SEGMENT[product]
    return "/".join(p for p in (method, segment, scenario, variable, member) if p)


def layout(gcm: str, *, product: str) -> dict:
    """Report what the store contains, as {method: {scenario: {variable: [members]}}}.

    Read from the store rather than transcribed. The walk is milliseconds once
    the store is open, and the result is cached.
    """
    _check_gcm(gcm)
    _check_product(product)
    return copy.deepcopy(_layout(gcm, product))


def _scenarios(gcm: str, method: str, product: str) -> dict:
    _check_gcm(gcm)
    _check_product(product)
    tree = _layout(gcm, product)
    if method not in tree:
        raise ValueError(
            f"method must be one of {sorted(tree)} for {_where(gcm, '', product)}, got {method!r}"
        )
    return tree[method]


def _variables(scenario: str, gcm: str, method: str, product: str) -> dict:
    scenarios = _scenarios(gcm, method, product)
    if scenario not in scenarios:
        raise ValueError(
            f"scenario must be one of {sorted(scenarios)} for {_where(gcm, method, product)}, "
            f"got {scenario!r}"
        )
    return scenarios[scenario]


def scenarios_for(gcm: str, method: str, *, product: str) -> list[str]:
    """Scenarios available for a GCM and method (g6_1p5k_end is CESM2-WACCM6 only)."""
    return sorted(_scenarios(gcm, method, product))


def variables_for(scenario: str, gcm: str, method: str, *, product: str) -> list[str]:
    """Variables available for a scenario. Not every member has every variable."""
    return sorted(_variables(scenario, gcm, method, product))


def members_for(scenario: str, variable: str, gcm: str, method: str, *, product: str) -> list[str]:
    """Ensemble members that contain a variable in a scenario.

    Most scenarios have several members, and they do not all have the same
    variables: on CESM2-WACCM6/ssp245, members 001-005 run to 2099 with
    tas/pr/rsds only, while 006-010 stop in 2069 and are the only ones with
    tasmax/tasmin. Both products contain the same members.
    """
    variables = _variables(scenario, gcm, method, product)
    if not isinstance(variable, str) or "," in variable:
        raise ValueError(
            f"choose one variable at a time, e.g. 'tas', not {variable!r}; "
            f"{_where(gcm, method, product, scenario)} contains {sorted(variables)}"
        )
    if variable not in variables:
        hint = ""
        if variable in COARSE_ONLY_VARIABLES and product != "debiased_coarse":
            hint = f"; {variable} is available only with product='debiased_coarse'"
        raise ValueError(
            f"{_where(gcm, method, product, scenario)} contains {sorted(variables)}, "
            f"not {variable!r}{hint}"
        )
    return list(variables[variable])


def _resolve_member(
    scenario: str, variable: str, gcm: str, method: str, member: str | None, product: str
) -> str:
    published = members_for(scenario, variable, gcm, method, product=product)
    if member in published:
        return member
    where = _where(gcm, method, product, scenario, variable)
    choices = ", ".join(
        f"{m} ({' to '.join(_coverage(gcm, _group_path(method, scenario, variable, m, product)))})"
        for m in published
    )
    problem = "no member given" if member is None else f"member {member!r} is not available"
    raise ValueError(f"{problem} for {where}; choose one of: {choices}")


def ensemble_member(
    scenario: str, variable: str, gcm: str, method: str, member: str | None, *, product: str
) -> str:
    """Check that `member` contains `variable` for this request, and return it.

    When `member` is missing or not available, the error lists the members that
    do contain the variable and the years each covers. Callers use this before
    building a filename or a group path.
    """
    return _resolve_member(scenario, variable, gcm, method, member, product)


@functools.cache
def _coverage(gcm: str, group_path: str):
    _, root = _open_root(gcm)
    time = root[group_path]["time"]
    stamps = xr.coding.times.decode_cf_datetime(
        np.asarray([time[0], time[-1]]),
        time.attrs["units"],
        time.attrs.get("calendar", "standard"),
    )
    return tuple(str(np.datetime_as_string(s, unit="D")) for s in stamps)


def coverage(
    scenario: str, variable: str, gcm: str, method: str, member: str, *, product: str
) -> tuple[str, str]:
    """Return the (first, last) date available, read from the store's time axis.

    Coverage varies by member, not by variable: on CESM2-WACCM6/ssp245, member
    003 runs to 2099 and member 008 stops in 2069.
    """
    resolved = _resolve_member(scenario, variable, gcm, method, member, product)
    path = _group_path(method, scenario, variable, resolved, product)
    return _coverage(gcm, path)


def check_members(scenario: str, variables, gcm: str, method: str, *, product: str) -> list[str]:
    """Report which members contain every variable in `variables`, and return them.

    Not every member has every variable: on CESM2-WACCM6/ssp245, members 001-005
    have tas/pr/rsds only, while 006-010 have all five. Loading each variable
    from one of the members listed here keeps them from the same model run.
    """
    variables = list(variables)
    per_variable = {v: members_for(scenario, v, gcm, method, product=product) for v in variables}
    common = sorted(set.intersection(*(set(members) for members in per_variable.values())))
    where = _where(gcm, method, product, scenario)
    if common:
        print(f"{where}: members containing {', '.join(variables)}: {', '.join(common)}")
    else:
        print(f"{where}: no single member contains all of {', '.join(variables)}")
        for v, members in per_variable.items():
            print(f"    {v:8s} {', '.join(members)}")
    return common


def qa_flag_vars(ds: xr.Dataset, variable: str | None = None) -> list[str]:
    """Names of the quality-flag variables in a group as loaded.

    A group holds its own variable plus zero or more binary flags, so a flag is
    every data variable that is not the group's variable. That rule holds for
    every published group, in both products. Matching on names does not:
    ``trend_distortion_flag`` has no ``qa_flag`` prefix.

    `variable` defaults to the group's ``srm_downscaling:variable`` attribute.
    Call this on a freshly loaded group -- anything you add afterwards would
    be counted as a flag too.
    """
    variable = variable or ds.attrs.get("srm_downscaling:variable")
    if variable is None:
        raise ValueError("cannot tell the data variable from the flags here; pass variable=")
    return sorted(str(v) for v in ds.data_vars if v != variable)


def load_downscaling_store(
    scenario: str,
    variable: str,
    gcm: str,
    method: str,
    member: str,
    qa_flags: bool = False,
    *,
    product: str,
) -> xr.Dataset:
    """Open one group from the published store, lazily.

    chunks={} adopts the store's own chunk grid. Passing chunks="auto" instead
    fuses native chunks into much larger dask tasks -- more memory per task for
    exactly the same bytes read.

    `qa_flags` defaults to False so the result holds exactly the variable you
    asked for. qa_flag_time_varying shares that variable's chunk grid, so
    keeping it doubles the bytes every later selection reads; opt in when you
    intend to use the flags. Which flags a group carries varies -- see
    qa_flag_vars().

    `product` is "downscaled" for the 0.25 degree data or "debiased_coarse" for
    the bias-corrected data on the GCM's native grid.
    """
    if method not in METHODS:
        raise ValueError(f"method must be one of {METHODS}, got {method!r}")
    # Also validates gcm, product, scenario, variable and member against the store.
    resolved = _resolve_member(scenario, variable, gcm, method, member, product)

    session, _ = _open_root(gcm)
    ds = xr.open_dataset(
        session.store,
        group=_group_path(method, scenario, variable, resolved, product),
        engine="zarr",
        consolidated=False,
        zarr_format=3,
        chunks={},
    )
    if not qa_flags:
        ds = ds.drop_vars(qa_flag_vars(ds, variable))
    return ds


def describe_request(da: xr.DataArray, label: str = "selection", quiet: bool = False) -> int:
    """Estimate what a selection costs before you load it.

    Returns the number of bytes that will actually be read, which is what
    matters: a chunk is the unit of decompression, so a request touching one
    cell of a chunk still reads the whole thing.
    """
    native = da.encoding.get("chunks") or da.encoding.get("preferred_chunks")
    if isinstance(native, dict):
        native = tuple(native[d] for d in da.dims)

    if native:
        source = "store chunks"
    elif da.chunks:
        native = tuple(c[0] for c in da.chunks)
        source = "dask chunks, store encoding dropped"
    else:
        native, source = da.shape, "already in memory"

    chunk_bytes = int(np.prod(native)) * da.dtype.itemsize
    n_chunks = getattr(getattr(da, "data", None), "npartitions", 1)
    read = n_chunks * chunk_bytes

    if not quiet:
        print(f"{label}:")
        print(f"  shape          {dict(zip(da.dims, da.shape))}")
        print(f"  logical size   {da.nbytes / 1e9:8.3f} GB")
        print(f"  chunks touched {n_chunks:8d}  ({chunk_bytes / 1e6:.1f} MB each, {source})")
        print(f"  data read      {read / 1e9:8.3f} GB")
    return read


_SEASONS = {
    (12, 1, 2): "DJF",
    (3, 4, 5): "MAM",
    (6, 7, 8): "JJA",
    (9, 10, 11): "SON",
}


def _month_tag(months) -> str:
    """Name a month filter: a season if it is one, else the month numbers."""
    key = tuple(sorted(months))
    for season, name in _SEASONS.items():
        if key == tuple(sorted(season)):
            return name
    return "".join(f"m{m:02d}" for m in key)


def _hemisphere(value: float, positive: str, negative: str) -> str:
    return f"{abs(value):g}{positive if value >= 0 else negative}"


def point_tag(lat: float, lon: float) -> str:
    """Filename prefix for a single point, with hemisphere letters: ``pt40N-105W``.

    Letters rather than signs keep the name unambiguous, since ``-`` also
    separates the two numbers.
    """
    return f"pt{_hemisphere(lat, 'N', 'S')}-{_hemisphere(lon, 'E', 'W')}"


def bbox_tag(lon_min: float, lat_min: float, lon_max: float, lat_max: float) -> str:
    """Filename prefix for a bounding box, in ``--bbox`` order: ``bbox-68E-6N-98E-38N``."""
    hemispheres = (("E", "W"), ("N", "S"), ("E", "W"), ("N", "S"))
    values = (lon_min, lat_min, lon_max, lat_max)
    return "bbox-" + "-".join(_hemisphere(v, *h) for v, h in zip(values, hemispheres))


def output_filename(
    scenario: str,
    variable: str,
    start: str | None = None,
    end: str | None = None,
    *,
    gcm: str,
    method: str,
    member: str,
    product: str,
    label: str | None = None,
    point: tuple[float, float] | None = None,
    months=None,
    suffix: str = ".nc",
) -> str:
    """Build a self-describing, collision-free output filename.

    Every field that distinguishes one download from another goes in the name:

        india_CESM2-WACCM6_bcsd_ssp245_003_tas_2050-2055.nc

    The ensemble member alone is not enough to tell downloads apart -- on
    CESM2-WACCM6 both ssp245/tas and g6_1p5k/tas have a member 003 -- so
    the scenario, GCM and method are all part of the name. The reverse matters
    too: one scenario contains up to ten members, so the member has to be in
    the name for those to land in separate files.

    The bias-corrected product would otherwise collide with the downscaled one
    for the same selection, so it tags the method field --
    ``..._bcsd-debiased-coarse_...`` -- while downscaled names carry the bare method.

    `label` is a free-text prefix describing the region or purpose; underscores
    in it are converted to hyphens so `_` stays a clean field separator. With no
    `label`, `point=(lat, lon)` names a single-point export by its coordinates
    -- ``pt28.6N-77.2E_...``, see point_tag() -- the same prefix the command-line
    tool uses.
    """
    if not label and point is not None:
        label = point_tag(*point)
    resolved = ensemble_member(scenario, variable, gcm, method, member, product=product)
    method_tag = method if product == "downscaled" else f"{method}-{product.replace('_', '-')}"
    bits = []
    if label:
        bits.append(str(label).strip().replace(" ", "-").replace("_", "-"))
    bits += [gcm, method_tag, scenario, resolved, variable]

    if start or end:
        span = "-".join(part[:4] for part in (start, end) if part)
        bits.append(span)
    if months:
        bits.append(_month_tag(months))

    if not suffix.startswith("."):
        suffix = f".{suffix}"
    return "_".join(bits) + suffix
