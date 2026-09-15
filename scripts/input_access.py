"""Access helpers for the processed GCM input data behind the SRM downscaling dataset.

The downscaling pipeline starts from harmonized copies of each GCM's daily
output: one icechunk store per GCM, one zarr group per scenario, and every
variable on ``(ensemble_member, time, lat, lon)``. Names, units, calendars and
longitudes are already standardized there. This module is the canonical home
for where those stores live and how to read them.

The stores sit on CarbonPlan's ``carbonplan-srm`` bucket until they move to
source.coop, so their location is kept in one constants block below.

Two things differ from the published output in data_access.py:

* **Members are a dimension, not groups.** A group's time axis spans the whole
  scenario, and a member that lacks a variable or some years holds NaN there.
* **Coverage comes from the chunk manifest.** The stores were written without
  all-NaN chunks, so the shards an array actually stores show which members
  carry it and over which years -- in about 0.1 s, without reading any data.
"""

from __future__ import annotations

import functools

import numpy as np
import xarray as xr

from data_access import _month_tag, describe_request, pinned_member

__all__ = [
    "INPUT_BUCKET",
    "INPUT_REGION",
    "INPUT_BRANCH",
    "GCMS",
    "VARIABLES",
    "layout",
    "scenarios_for",
    "variables_for",
    "members_for",
    "ensemble_member",
    "coverage",
    "shard_days",
    "load_input_store",
    "describe_request",
    "output_filename",
]

# Where the stores live. Everything that changes when they move to source.coop
# is in this block.
INPUT_BUCKET = "carbonplan-srm"
INPUT_REGION = "us-west-2"
_INPUT_PREFIX = "input/processed"
INPUT_BRANCH = "main"

# The S3 store names predate the model-name correction (#598) and cannot be
# renamed; users only ever see the keys. A cesm2_waccm.icechunk (underscore)
# also exists next to cesm2-waccm.icechunk and is empty -- never point at it.
_STORES = {"CESM2-WACCM6": "cesm2-waccm", "UKESM1-1-LL": "ukesm"}
GCMS = list(_STORES)

# The advertised set, so `--help` does not touch the network. What a scenario
# actually holds comes from the store: see variables_for().
VARIABLES = ["tas", "tasmax", "tasmin", "pr", "rsds", "hurs"]


def _check_gcm(gcm: str) -> None:
    if gcm not in _STORES:
        raise ValueError(f"gcm must be one of {GCMS}, got {gcm!r}")


def _store_url(gcm: str) -> str:
    return f"s3://{INPUT_BUCKET}/{_INPUT_PREFIX}/{_STORES[gcm]}.icechunk"


@functools.cache
def _session(gcm: str):
    """A read-only session on the store's branch. Cached: one manifest fetch per GCM."""
    import icechunk

    _check_gcm(gcm)
    storage = icechunk.s3_storage(
        bucket=INPUT_BUCKET,
        prefix=f"{_INPUT_PREFIX}/{_STORES[gcm]}.icechunk",
        anonymous=True,
        region=INPUT_REGION,
    )
    try:
        return icechunk.Repository.open(storage).readonly_session(branch=INPUT_BRANCH)
    except Exception as exc:  # icechunk raises its own error types
        raise RuntimeError(
            f"could not open {_store_url(gcm)} (region {INPUT_REGION}, branch "
            f"{INPUT_BRANCH}) anonymously: {exc}"
        ) from exc


@functools.cache
def _root(gcm: str):
    import zarr

    return zarr.open_group(_session(gcm).store, mode="r", zarr_format=3)


def scenarios_for(gcm: str = "CESM2-WACCM6") -> list[str]:
    """Scenario groups in a GCM's input store."""
    _check_gcm(gcm)
    return sorted(_root(gcm).group_keys())


@functools.cache
def _group(gcm: str, scenario: str) -> xr.Dataset:
    scenarios = scenarios_for(gcm)
    if scenario not in scenarios:
        raise ValueError(f"scenario must be one of {scenarios} for {gcm} input, got {scenario!r}")
    return xr.open_dataset(
        _session(gcm).store,
        group=scenario,
        engine="zarr",
        consolidated=False,
        zarr_format=3,
        chunks={},
    )


def variables_for(scenario: str, gcm: str = "CESM2-WACCM6") -> list[str]:
    """Variables a scenario group holds. Not every member carries every one."""
    return sorted(str(v) for v in _group(gcm, scenario).data_vars)


@functools.cache
def _stored_shards(gcm: str, scenario: str, variable: str) -> dict[str, tuple[int, ...]]:
    """{member: sorted time-shard indices that hold data} for one array, from the manifest."""
    from zarr.core.sync import sync

    variables = variables_for(scenario, gcm)
    if variable not in variables:
        raise ValueError(f"{gcm} input {scenario} holds {variables}, not {variable!r}")

    async def collect():
        return [c async for c in _session(gcm).chunk_coordinates(f"/{scenario}/{variable}")]

    # sync() runs on zarr's own event loop, so this also works inside Jupyter,
    # where asyncio.run() would fail because the kernel's loop is already running.
    shards: dict[int, set[int]] = {}
    for member_index, time_index, *_ in sync(collect()):
        shards.setdefault(member_index, set()).add(time_index)
    members = [str(m) for m in _group(gcm, scenario).ensemble_member.values]
    return {members[i]: tuple(sorted(t)) for i, t in sorted(shards.items())}


def members_for(scenario: str, variable: str = "tas", gcm: str = "CESM2-WACCM6") -> list[str]:
    """Members that hold any data for a variable, in the store's member order.

    A member whose array is entirely NaN -- ssp245 tasmax for CESM2-WACCM6
    members 001-005, for instance -- stores no shards and is left out.
    """
    stored = _stored_shards(gcm, scenario, variable)
    order = [str(m) for m in _group(gcm, scenario).ensemble_member.values]
    return [m for m in order if m in stored]


def layout(gcm: str = "CESM2-WACCM6") -> dict[str, dict[str, list[str]]]:
    """What a GCM's input store holds, as {scenario: {variable: [members]}}."""
    return {
        scenario: {v: members_for(scenario, v, gcm) for v in variables_for(scenario, gcm)}
        for scenario in scenarios_for(gcm)
    }


@functools.cache
def _array(gcm: str, scenario: str, variable: str):
    import zarr

    variables = variables_for(scenario, gcm)
    if variable not in variables:
        raise ValueError(f"{gcm} input {scenario} holds {variables}, not {variable!r}")
    return zarr.open_array(_session(gcm).store, path=f"{scenario}/{variable}", mode="r", zarr_format=3)


def shard_days(scenario: str, variable: str = "tas", gcm: str = "CESM2-WACCM6") -> int:
    """Days one stored shard spans: the resolution of coverage(..., exact=False)."""
    arr = _array(gcm, scenario, variable)
    return int((arr.shards or arr.chunks)[1])


def ensemble_member(
    scenario: str, variable: str, gcm: str = "CESM2-WACCM6", member: str | None = None
) -> str:
    """Which member a request resolves to, validated against the store.

    Omitting `member` takes the member pinned for the downscaled output
    (data_access.pinned_member), so the default input is the run the default
    downscaled data was built from.
    """
    published = members_for(scenario, variable, gcm)
    where = f"{gcm} input {scenario}/{variable}"
    if member is not None:
        if member not in published:
            raise ValueError(f"member {member!r} holds no data for {where}; available: {published}")
        return member
    default = pinned_member(gcm, scenario, variable)
    if default not in published:
        raise ValueError(
            f"no usable default member for {where}; pass member= explicitly, one of {published}"
        )
    return default


def _day(value) -> str:
    return str(np.datetime_as_string(np.datetime64(value, "D"), unit="D"))


def _edge(arr, member_index: int, shard_index: int, lat_i: int, lon_i: int, which: str) -> int:
    """Time index of the first or last finite value in one stored shard, at one grid point.

    Binary search over the shard's inner chunks, assuming coverage is contiguous
    within the shard: about five chunk reads per edge.
    """
    shard_len = (arr.shards or arr.chunks)[1]
    chunk_len = arr.chunks[1]
    n_time = arr.shape[1]
    lo_t = shard_index * shard_len
    hi_t = min(lo_t + shard_len, n_time)
    starts = list(range(lo_t, hi_t, chunk_len))

    def finite(k):
        return np.isfinite(arr[member_index, starts[k] : min(starts[k] + chunk_len, hi_t), lat_i, lon_i])

    lo, hi = 0, len(starts) - 1
    while lo < hi:
        if which == "last":
            mid = (lo + hi + 1) // 2
            lo, hi = (mid, hi) if finite(mid).any() else (lo, mid - 1)
        else:
            mid = (lo + hi) // 2
            lo, hi = (lo, mid) if finite(mid).any() else (mid + 1, hi)
    hits = np.flatnonzero(finite(lo))
    if hits.size == 0:
        raise RuntimeError(
            f"shard {shard_index} is stored but holds no finite value at the probe point; the "
            "store was probably rewritten with all-NaN chunks, so the manifest can no longer be "
            "trusted as a coverage source"
        )
    return starts[lo] + int(hits[-1] if which == "last" else hits[0])


def coverage(
    scenario: str,
    variable: str,
    gcm: str = "CESM2-WACCM6",
    member: str | None = None,
    exact: bool = False,
) -> tuple[str, str]:
    """The (first, last) date a member holds data for a variable.

    By default this reads only the chunk manifest, so the span is accurate to
    one shard (480 days for CESM2-WACCM6, 960 for UKESM1-1-LL) and always
    contains the true span. `exact=True` pins it to the day with a binary search
    over the two boundary shards at one grid point: about ten 6.6 MB chunk reads.
    """
    resolved = ensemble_member(scenario, variable, gcm, member)
    shards = _stored_shards(gcm, scenario, variable)[resolved]
    times = _group(gcm, scenario).time.values
    arr = _array(gcm, scenario, variable)
    if not exact:
        shard_len = shard_days(scenario, variable, gcm)
        last = min((shards[-1] + 1) * shard_len, len(times)) - 1
        return _day(times[shards[0] * shard_len]), _day(times[last])
    member_index = [str(m) for m in _group(gcm, scenario).ensemble_member.values].index(resolved)
    lat_i, lon_i = arr.shape[2] // 2, arr.shape[3] // 2
    first = _edge(arr, member_index, shards[0], lat_i, lon_i, "first")
    last = _edge(arr, member_index, shards[-1], lat_i, lon_i, "last")
    return _day(times[first]), _day(times[last])


def _correct_model(ds: xr.Dataset, gcm: str) -> xr.Dataset:
    """Make the `model` attribute match the GCM's current name, recording any change.

    The CESM2-WACCM6 store still says "CESM2-WACCM": the model was renamed in
    carbonplan/srm-downscaling#598 after the store was written. Mirrors the
    note upstream already writes for UKESM1-1-LL, and changes nothing once the
    stored value is correct. Provenance attributes such as source_id are left alone.
    """
    stored = ds.attrs.get("model")
    if stored == gcm:
        return ds
    ds.attrs["model"] = gcm
    if "model_id_correction" not in ds.attrs:
        ds.attrs["model_id_correction"] = (
            f"Stored model attribute {stored!r} replaced with {gcm} when loaded by "
            "input_access.py: the model was renamed in carbonplan/srm-downscaling#598 after "
            "this input store was written."
        )
    return ds


def load_input_store(
    scenario: str, variable: str = "tas", gcm: str = "CESM2-WACCM6", member: str | None = None
) -> xr.Dataset:
    """Open one member's variable from a GCM's input store, lazily.

    Returns dims (time, lat, lon), with the member kept as a scalar
    ensemble_member coordinate. The time axis is the scenario's full axis:
    outside coverage(...) the values are NaN. It is not trimmed, because an
    exact trim costs reads -- call coverage(..., exact=True) when you need it.
    """
    resolved = ensemble_member(scenario, variable, gcm, member)
    ds = _group(gcm, scenario)[[variable]].sel(ensemble_member=resolved)
    # The store keeps member IDs as fixed-width unicode, which Zarr v3 has no
    # specification for: writing it warns and other libraries may not read it.
    # A variable-length string round-trips to both Zarr and NetCDF.
    ds = ds.assign_coords(ensemble_member=ds.ensemble_member.astype(object))
    # The group dataset is cached; give this result its own attrs before editing them.
    ds.attrs = dict(ds.attrs)
    return _correct_model(ds, gcm)


def output_filename(
    scenario: str,
    variable: str,
    start: str | None = None,
    end: str | None = None,
    *,
    gcm: str = "CESM2-WACCM6",
    member: str | None = None,
    label: str | None = None,
    months=None,
    suffix: str = ".nc",
) -> str:
    """A self-describing filename, in data_access.output_filename's format with `input` as the method:

        delhi_CESM2-WACCM6_input_ssp245_003_tas_2050-2059.nc
    """
    resolved = ensemble_member(scenario, variable, gcm, member)
    bits = []
    if label:
        bits.append(str(label).strip().replace(" ", "-").replace("_", "-"))
    bits += [gcm, "input", scenario, resolved, variable]
    if start or end:
        bits.append("-".join(part[:4] for part in (start, end) if part))
    if months:
        bits.append(_month_tag(months))
    if not suffix.startswith("."):
        suffix = f".{suffix}"
    return "_".join(bits) + suffix
