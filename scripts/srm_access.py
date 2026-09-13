"""Shared access helpers for the CarbonPlan SRM downscaling dataset.

This module is the canonical home for the details that change when the
dataset is republished: which store to open, the pinned branch, the group
layout, and which ensemble member a bare request resolves to. Keeping them in
one place matters -- the notebook in this repository once sat broken for a
whole release because a dead store path was hard-coded in a second location.

Group layout as of v1.0.0::

    {method}/{scenario}/{variable}/{member}

**Nothing about that tree is transcribed here.** The published store is the
authority. Opening a branch pulls one immutable manifest, after which walking
the whole hierarchy costs milliseconds, so ``layout()`` reads the tree rather
than keeping a hand-maintained table that goes stale every release. v1.0.0
turned the dataset into a real ensemble -- up to ten members for one
CESM2-WACCM6 scenario -- which a literal table could no longer carry.

v1.0.0 also publishes ``{method}/debiased_coarse/{scenario}/{variable}/{member}``:
the debiased GCM fields at their native resolution, before downscaling. Those
are pipeline diagnostics rather than the 0.25 degree product, so they are
excluded from everything below.
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
    "METHODS",
    "VARIABLES",
    "QA_PREFIX",
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
]

BUCKET = "us-west-2.opendata.source.coop"
REGION = "us-west-2"
_PREFIX = "carbonplan/srm-downscaling/output/production"

# There are zero tags on these stores, so pinning a branch is the only way to
# get reproducible reads.
STORE_BRANCH = "v1.0.0"

# One store per GCM. Only these two publish v1.0.0; MIROC-ES2H exists but is
# still at v0.13.0, which has a different group layout, so it is not offered.
_STORES = {
    "CESM2-WACCM6": "CESM2-WACCM6-ERA5-global",
    "UKESM1-1-LL": "UKESM1-1-LL-ERA5-global",
}
GCMS = list(_STORES)

# The advertised sets, kept as literals so `--help` and error messages do not
# have to touch the network. What a *given* combination actually publishes
# comes from the store: see variables_for() and members_for().
METHODS = ["bcsd", "qdmsd"]
VARIABLES = ["tas", "tasmax", "tasmin", "pr", "rsds"]

# Sits alongside the scenarios under each method, holding the debiased GCM
# fields at native resolution. Not the downscaled product; skipped everywhere.
_DIAGNOSTIC_GROUP = "debiased_coarse"

# v1.0.0 ships quality flags as ordinary data variables in some groups. They
# share the data variable's chunk grid, so carrying them along doubles the
# bytes read -- hence load_downscaling_store(qa_flags=False) by default.
QA_PREFIX = "qa_flag"

# Which member a bare (scenario, variable) request resolves to. This is the one
# piece of editorial judgement in the module -- the store publishes several
# members and cannot say which one a newcomer should get -- so it is written
# out rather than derived. Each pin is checked against the published tree
# before it is used, so a member retired in a later release fails loudly.
#
# These reproduce the single members published before v1.0.0, whose data is
# byte-identical there, so pinning the new branch changes no existing result.
# "*" is the fallback for any variable without its own entry.
_DEFAULT_MEMBERS = {
    "CESM2-WACCM6": {
        "historical": {"*": "r3i1p1f1", "tasmax": "001", "tasmin": "001"},
        "ssp245": {"*": "003", "tasmax": "008", "tasmin": "008"},
        "g6_1p5k": {"*": "003"},
        "g6_1p5k_end": {"*": "002"},
    },
    "UKESM1-1-LL": {
        "historical": {"*": "u-by791"},
        "ssp245": {"*": "r2i1p1f2"},
        "g6_1p5k": {"*": "r2i1p1f2"},
    },
}


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


@functools.cache
def _open_root(gcm: str, branch: str):
    """Open a store's root group. Cached: one manifest fetch per (gcm, branch)."""
    import icechunk
    import zarr

    storage = icechunk.s3_storage(
        bucket=BUCKET,
        prefix=f"{_PREFIX}/{_STORES[gcm]}.icechunk",
        anonymous=True,
        region=REGION,
    )
    session = icechunk.Repository.open(storage).readonly_session(branch=branch)
    return session, zarr.open_group(session.store, mode="r", zarr_format=3)


@functools.cache
def _layout(gcm: str, branch: str) -> dict:
    _, root = _open_root(gcm, branch)
    tree = {}
    for method in sorted(root.group_keys()):
        scenarios = {}
        for scenario in sorted(root[method].group_keys()):
            if scenario == _DIAGNOSTIC_GROUP:
                continue
            scenarios[scenario] = {
                variable: sorted(root[f"{method}/{scenario}/{variable}"].group_keys())
                for variable in sorted(root[f"{method}/{scenario}"].group_keys())
            }
        tree[method] = scenarios
    return tree


def layout(gcm: str = "CESM2-WACCM6", branch: str | None = None) -> dict:
    """Report what the store actually publishes, as {method: {scenario: {variable: [members]}}}.

    Read from the store rather than transcribed, so it cannot go stale. The
    walk is milliseconds once the branch is open, and the result is cached.
    """
    _check_gcm(gcm)
    return copy.deepcopy(_layout(gcm, branch or STORE_BRANCH))


def _check_gcm(gcm: str) -> None:
    if gcm not in _STORES:
        raise ValueError(f"gcm must be one of {GCMS}, got {gcm!r}")


def _methods(gcm: str, branch: str | None = None) -> dict:
    _check_gcm(gcm)
    return _layout(gcm, branch or STORE_BRANCH)


def _scenarios(gcm: str, method: str, branch: str | None = None) -> dict:
    tree = _methods(gcm, branch)
    if method not in tree:
        raise ValueError(f"method must be one of {sorted(tree)} for {gcm}, got {method!r}")
    return tree[method]


def _variables(scenario: str, gcm: str, method: str, branch: str | None = None) -> dict:
    scenarios = _scenarios(gcm, method, branch)
    if scenario not in scenarios:
        raise ValueError(
            f"scenario must be one of {sorted(scenarios)} for {gcm}/{method}, got {scenario!r}"
        )
    return scenarios[scenario]


def scenarios_for(gcm: str = "CESM2-WACCM6", method: str = "bcsd") -> list[str]:
    """Scenarios published for a given GCM (g6_1p5k_end is CESM2-WACCM6 only)."""
    return sorted(_scenarios(gcm, method))


def variables_for(scenario: str, gcm: str = "CESM2-WACCM6", method: str = "bcsd") -> list[str]:
    """Variables published for a scenario. Not every member carries every variable."""
    return sorted(_variables(scenario, gcm, method))


def members_for(
    scenario: str, variable: str = "tas", gcm: str = "CESM2-WACCM6", method: str = "bcsd"
) -> list[str]:
    """Ensemble members published for a (scenario, variable) pair.

    v1.0.0 publishes several members for most scenarios, and they do not all
    carry the same variables: on CESM2-WACCM6/ssp245, members 001-005 run to
    2099 with tas/pr/rsds only, while 006-010 stop in 2069 and are the only
    ones with tasmax/tasmin.
    """
    variables = _variables(scenario, gcm, method)
    if variable not in variables:
        raise ValueError(
            f"{gcm}/{method}/{scenario} publishes {sorted(variables)}, not {variable!r}"
        )
    return list(variables[variable])


def _resolve_member(
    scenario: str, variable: str, gcm: str, method: str, member: str | None
) -> str:
    published = members_for(scenario, variable, gcm, method)

    if member is not None:
        if member not in published:
            raise ValueError(
                f"member {member!r} is not published for {gcm}/{method}/{scenario}/{variable}; "
                f"available: {published}"
            )
        return member

    pins = _DEFAULT_MEMBERS.get(gcm, {}).get(scenario, {})
    default = pins.get(variable, pins.get("*"))
    if default is None:
        raise ValueError(
            f"no default member pinned for {gcm}/{scenario}/{variable}; "
            f"pass member= explicitly, one of {published}"
        )
    if default not in published:
        raise ValueError(
            f"the pinned default member {default!r} is no longer published for "
            f"{gcm}/{method}/{scenario}/{variable} on branch {STORE_BRANCH}; "
            f"pass member= explicitly, one of {published}"
        )
    return default


def ensemble_member(
    scenario: str,
    variable: str,
    gcm: str = "CESM2-WACCM6",
    method: str = "bcsd",
    member: str | None = None,
) -> str:
    """Report which member a (gcm, scenario, variable) request resolves to.

    Passing `member` validates it against the store and hands it back, so this
    is also the one place callers need to build a filename or a group path.
    """
    return _resolve_member(scenario, variable, gcm, method, member)


@functools.cache
def _coverage(gcm: str, method: str, scenario: str, variable: str, member: str, branch: str):
    _, root = _open_root(gcm, branch)
    group = root[f"{method}/{scenario}/{variable}/{member}"]
    time = group["time"]
    stamps = xr.coding.times.decode_cf_datetime(
        np.asarray([time[0], time[-1]]),
        time.attrs["units"],
        time.attrs.get("calendar", "standard"),
    )
    return tuple(str(np.datetime_as_string(s, unit="D")) for s in stamps)


def coverage(
    scenario: str,
    variable: str,
    gcm: str = "CESM2-WACCM6",
    method: str = "bcsd",
    member: str | None = None,
) -> tuple[str, str]:
    """Return the (first, last) date available, read from the store's time axis.

    Coverage varies by member, not by variable: on CESM2-WACCM6/ssp245, member
    003 runs to 2099 and member 008 stops in 2069.
    """
    resolved = _resolve_member(scenario, variable, gcm, method, member)
    return _coverage(gcm, method, scenario, variable, resolved, STORE_BRANCH)


def check_members(
    scenario: str, variables, gcm: str = "CESM2-WACCM6", method: str = "bcsd"
) -> dict:
    """Map each variable to its default member, warning when they disagree.

    On CESM2-WACCM6 the temperature extremes come from a different batch of
    members than tas/pr/rsds, so the defaults for tas and tasmax do not match
    and combining them mixes realizations. Since v1.0.0 that is usually
    avoidable: several members carry every variable, and this reports them.
    """
    members = {v: ensemble_member(scenario, v, gcm, method) for v in variables}
    if len(set(members.values())) == 1:
        shared = next(iter(set(members.values())))
        print(f"{gcm}/{scenario}: {', '.join(members)} all share member {shared}")
        return members

    print(f"WARNING: on {gcm}/{scenario} these variables span multiple ensemble members:")
    for v, m in members.items():
        print(f"    {v:8s} -> {m}")
    print("  Combining them mixes members, which is rarely intended.")

    common = set.intersection(*(set(members_for(scenario, v, gcm, method)) for v in variables))
    if common:
        print(f"  Members carrying all of {list(variables)}: {sorted(common)}")
        print(f"  Pass member= to load them from one realization, e.g. member={sorted(common)[0]!r}.")
    else:
        print(f"  No single member carries all of {list(variables)} in this scenario.")
    return members


def qa_flag_vars(ds: xr.Dataset) -> list[str]:
    """Names of the quality-flag variables present, which is not every group."""
    return sorted(v for v in ds.data_vars if str(v).startswith(QA_PREFIX))


def load_downscaling_store(
    scenario: str,
    variable: str = "tas",
    gcm: str = "CESM2-WACCM6",
    method: str = "bcsd",
    member: str | None = None,
    qa_flags: bool = False,
) -> xr.Dataset:
    """Open one group from the published store, lazily.

    chunks={} adopts the store's own chunk grid. Passing chunks="auto" instead
    fuses native chunks into much larger dask tasks -- more memory per task for
    exactly the same bytes read.

    `qa_flags` defaults to False so the result holds exactly the variable you
    asked for. The flags share that variable's chunk grid, so keeping them
    doubles the bytes every later selection reads; opt in when you intend to
    use them. Not every group publishes them -- see qa_flag_vars().
    """
    if method not in METHODS:
        raise ValueError(f"method must be one of {METHODS}, got {method!r}")
    # Also validates gcm, scenario, variable and member against the store.
    resolved = _resolve_member(scenario, variable, gcm, method, member)

    session, _ = _open_root(gcm, STORE_BRANCH)
    ds = xr.open_dataset(
        session.store,
        group=f"{method}/{scenario}/{variable}/{resolved}",
        engine="zarr",
        consolidated=False,
        zarr_format=3,
        chunks={},
    )
    if not qa_flags:
        ds = ds.drop_vars(qa_flag_vars(ds))
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


def output_filename(
    scenario: str,
    variable: str,
    start: str | None = None,
    end: str | None = None,
    *,
    gcm: str = "CESM2-WACCM6",
    method: str = "bcsd",
    member: str | None = None,
    label: str | None = None,
    months=None,
    suffix: str = ".nc",
) -> str:
    """Build a self-describing, collision-free output filename.

    Every field that distinguishes one download from another goes in the name:

        india_CESM2-WACCM6_bcsd_ssp245_003_tas_2050-2055.nc

    The ensemble member alone is not enough to tell downloads apart -- on
    CESM2-WACCM6 both ssp245/tas and g6_1p5k/tas default to member 003 -- so
    the scenario, GCM and method are all part of the name. Since v1.0.0 the
    reverse matters too: one scenario publishes up to ten members, so the
    member has to be in the name for those to land in separate files.

    `label` is a free-text prefix describing the region or purpose; underscores
    in it are converted to hyphens so `_` stays a clean field separator.
    """
    resolved = ensemble_member(scenario, variable, gcm, method, member)
    bits = []
    if label:
        bits.append(str(label).strip().replace(" ", "-").replace("_", "-"))
    bits += [gcm, method, scenario, resolved, variable]

    if start or end:
        span = "-".join(part[:4] for part in (start, end) if part)
        bits.append(span)
    if months:
        bits.append(_month_tag(months))

    if not suffix.startswith("."):
        suffix = "." + suffix
    return "_".join(bits) + suffix
