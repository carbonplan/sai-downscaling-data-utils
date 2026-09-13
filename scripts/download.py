#!/usr/bin/env python
"""Download a subset of the CarbonPlan SRM downscaling dataset.

A command-line counterpart to notebooks/subsetting-and-exporting.ipynb, for
when you want a file rather than an interactive session.

Examples
--------
Estimate the cost of a request without downloading anything::

    python scripts/download.py --scenario ssp245 --start 2050-01-01 \
        --end 2059-12-31 --bbox 68 6 98 38 --dry-run

Download a single-point time series::

    python scripts/download.py --scenario historical --variable tas \
        --point 28.6 77.2 --start 1990-01-01 --end 1999-12-31 \
        --output delhi.nc

See which ensemble members a scenario publishes, and what each one covers::

    python scripts/download.py --scenario ssp245 --list-members
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from srm_access import (  # noqa: E402
    GCMS,
    METHODS,
    STORE_BRANCH,
    VARIABLES,
    coverage,
    describe_request,
    ensemble_member,
    load_downscaling_store,
    members_for,
    output_filename,
    qa_flag_vars,
    variables_for,
)

# Written out rather than discovered, so `--help` never touches the network.
# argparse also cannot express "scenarios valid for the chosen GCM", so this is
# the union; the loader rejects an unavailable combination with a message
# naming what that GCM/method actually publishes.
ALL_SCENARIOS = ["g6_1p5k", "g6_1p5k_end", "historical", "ssp245"]

# A request reading more than this prompts for confirmation. Chunks span about
# a year each, so a global request reaches tens of GB very easily.
PROMPT_ABOVE_GB = 5.0


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="download.py",
        description="Download a spatial/temporal subset of the SRM downscaling dataset.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Examples")[-1],
    )
    p.add_argument("--scenario", required=True, choices=ALL_SCENARIOS)
    p.add_argument("--gcm", default="CESM2-WACCM6", choices=GCMS)
    p.add_argument("--method", default="bcsd", choices=METHODS,
                   help="downscaling method (default: bcsd)")
    p.add_argument("--variable", default="tas", choices=VARIABLES)
    p.add_argument(
        "--member",
        help="ensemble member (default: the pinned member for this scenario/variable); "
             "run --list-members to see what a scenario publishes",
    )
    p.add_argument(
        "--list-members", action="store_true",
        help="list the members published for --scenario, with coverage, then exit",
    )
    p.add_argument("--start", help="ISO start date, e.g. 2050-01-01")
    p.add_argument("--end", help="ISO end date, e.g. 2059-12-31")

    region = p.add_mutually_exclusive_group()
    region.add_argument(
        "--bbox", nargs=4, type=float, metavar=("LON_MIN", "LAT_MIN", "LON_MAX", "LAT_MAX")
    )
    region.add_argument("--point", nargs=2, type=float, metavar=("LAT", "LON"))

    p.add_argument("--output", type=Path, help="output path (default derived from selection)")
    p.add_argument("--format", default="netcdf", choices=["netcdf", "zarr"])
    p.add_argument(
        "--qa-flags", action="store_true",
        help="also write the quality flag variables. They share the data's chunk grid, "
             "so this roughly doubles the bytes read",
    )
    p.add_argument("--dry-run", action="store_true", help="report cost, download nothing")
    p.add_argument("--yes", "-y", action="store_true", help="skip the confirmation prompt")
    return p.parse_args(argv)


def validate_dates(args, member: str, first: str, last: str) -> None:
    """Fail loudly on out-of-range dates instead of writing an empty file."""
    for name, value in (("--start", args.start), ("--end", args.end)):
        if value is None:
            continue
        try:
            stamp = pd.Timestamp(value)
        except ValueError:
            raise SystemExit(f"error: {name} {value!r} is not a valid date")
        if not (pd.Timestamp(first) <= stamp <= pd.Timestamp(last)):
            raise SystemExit(
                f"error: {name} {value} is outside {args.scenario}/{args.variable}/{member} "
                f"coverage ({first} to {last}). Selecting outside it yields no data. "
                "Coverage varies by member -- run --list-members to compare."
            )
    if args.start and args.end and pd.Timestamp(args.start) > pd.Timestamp(args.end):
        raise SystemExit("error: --start is after --end")


def _human(nbytes: int) -> str:
    """Format a byte count without collapsing small files to '0.0 MB'."""
    for unit, scale in (("GB", 1e9), ("MB", 1e6), ("kB", 1e3)):
        if nbytes >= scale:
            return f"{nbytes / scale:.1f} {unit}"
    return f"{nbytes} B"


def default_output(args, member: str) -> Path:
    """Self-describing filename, so downloads never overwrite one another."""
    if args.point:
        label = f"pt{args.point[0]:g}-{args.point[1]:g}"
    elif args.bbox:
        label = "bbox-" + "-".join(f"{v:g}" for v in args.bbox)
    else:
        label = "global"
    return Path(
        output_filename(
            args.scenario, args.variable, args.start, args.end,
            gcm=args.gcm, method=args.method, member=member, label=label,
            suffix=".zarr" if args.format == "zarr" else ".nc",
        )
    )


def list_members(args) -> int:
    """Print what a scenario publishes: members, coverage, and variables each carries.

    Coverage is a property of the member, not the variable -- on CESM2-WACCM6
    ssp245, members 001-005 run to 2099 while 006-010 stop in 2069 and are the
    only ones carrying tasmax/tasmin -- so this is the table you need before
    choosing one.
    """
    variables = variables_for(args.scenario, args.gcm, args.method)
    carried: dict[str, list[str]] = {}
    for variable in variables:
        for member in members_for(args.scenario, variable, args.gcm, args.method):
            carried.setdefault(member, []).append(variable)

    print(f"{args.gcm}/{args.method}/{args.scenario} (branch {STORE_BRANCH})")
    print(f"{'member':12s} {'coverage':25s} variables")
    for member in sorted(carried):
        first, last = coverage(
            args.scenario, carried[member][0], args.gcm, args.method, member=member
        )
        print(f"{member:12s} {first} to {last}  {' '.join(sorted(carried[member]))}")

    defaults = {v: ensemble_member(args.scenario, v, args.gcm, args.method) for v in variables}
    print("\ndefault member per variable (used when --member is omitted):")
    for variable, member in sorted(defaults.items()):
        print(f"  {variable:8s} -> {member}")
    return 0


def main(argv=None) -> int:
    args = parse_args(argv)

    try:
        if args.list_members:
            return list_members(args)

        member = ensemble_member(args.scenario, args.variable, args.gcm, args.method, args.member)
        ds = load_downscaling_store(
            args.scenario, args.variable, gcm=args.gcm, method=args.method,
            member=member, qa_flags=args.qa_flags,
        )
    except ValueError as exc:
        raise SystemExit(f"error: {exc}")

    # Read coverage off the axis we just opened rather than a transcribed table,
    # so it is always the member's own record.
    first, last = (str(ds.time.values[i])[:10] for i in (0, -1))
    validate_dates(args, member, first, last)

    print(f"{args.gcm}/{args.method}/{args.scenario}/{args.variable} -> member {member} "
          f"(branch {STORE_BRANCH})")
    print(f"coverage: {first} to {last}")

    if args.start or args.end:
        ds = ds.sel(time=slice(args.start, args.end))
    if args.point:
        lat, lon = args.point
        ds = ds.sel(lat=lat, lon=lon, method="nearest")
    elif args.bbox:
        lon_min, lat_min, lon_max, lat_max = args.bbox
        ds = ds.sel(lat=slice(lat_min, lat_max), lon=slice(lon_min, lon_max))

    if ds[args.variable].size == 0:
        raise SystemExit("error: selection is empty; check the dates and region")

    read_bytes = describe_request(ds[args.variable], "requested subset")
    flags = qa_flag_vars(ds)
    for flag in flags:
        read_bytes += describe_request(ds[flag], flag)
    if flags:
        print(f"total data read  {read_bytes / 1e9:8.3f} GB (variable + {len(flags)} flags)")

    if args.dry_run:
        print("\ndry run - nothing downloaded")
        return 0

    read_gb = read_bytes / 1e9
    if read_gb > PROMPT_ABOVE_GB and not args.yes:
        if not sys.stdin.isatty():
            raise SystemExit(
                f"error: this reads {read_gb:.1f} GB, above the {PROMPT_ABOVE_GB:g} GB "
                "threshold, and stdin is not a terminal. Re-run with --yes to proceed."
            )
        reply = input(f"\nThis will read {read_gb:.1f} GB. Continue? [y/N] ").strip().lower()
        if reply not in ("y", "yes"):
            print("aborted")
            return 1

    out = args.output or default_output(args, member)
    print(f"\nwriting {out} ...")

    # Drop encoding inherited from the source store. It still describes the full
    # 3-D grid -- chunks (365, 36, 72) and shards (1095, 180, 360) -- so writing
    # a reduced selection with it raises an arity error in zarr.
    out_ds = ds
    for name in out_ds.variables:
        out_ds[name].encoding = {}

    if args.format == "zarr":
        out_ds.to_zarr(out, mode="w")
    else:
        # NetCDF attrs cannot hold None, which the store uses for an unset
        # provenance field such as ssp245_ensemble_member.
        out_ds.attrs = {k: ("" if v is None else v) for k, v in out_ds.attrs.items()}
        out_ds.to_netcdf(out)

    size = sum(f.stat().st_size for f in out.rglob("*")) if out.is_dir() else out.stat().st_size
    print(f"wrote {out} ({_human(size)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
