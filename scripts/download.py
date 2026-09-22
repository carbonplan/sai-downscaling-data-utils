#!/usr/bin/env python
"""Download a subset of the CarbonPlan SRM downscaling dataset.

A command-line counterpart to notebooks/subsetting-and-exporting.ipynb, for
when you want a file rather than an interactive session.

Examples
--------
Estimate the cost of a request without downloading anything::

    pixi run download --scenario ssp245 --gcm CESM2-WACCM6 --method bcsd \
        --product downscaled --variable tas --member 003 \
        --start 2050-01-01 --end 2059-12-31 --bbox 68 6 98 38 --dry-run

Download a single-point time series::

    pixi run download --scenario historical --gcm CESM2-WACCM6 --method bcsd \
        --product downscaled --variable tas --member r3i1p1f1 \
        --point 28.6 77.2 --start 1990-01-01 --end 1999-12-31 --output delhi.nc

See which ensemble members a scenario contains, and what each one covers::

    pixi run download --scenario ssp245 --gcm CESM2-WACCM6 --method bcsd \
        --product downscaled --list-members

Download the bias-corrected data on the GCM's own grid, before downscaling::

    pixi run download --scenario ssp245 --gcm CESM2-WACCM6 --method bcsd \
        --product debiased_coarse --variable dtr --member 008 \
        --point 28.6 77.2 --start 2050-01-01 --end 2059-12-31

Download the GCM input data the pipeline started from, before bias correction::

    pixi run download --scenario ssp245 --gcm CESM2-WACCM6 --product input \
        --variable tas --member 003 --point 28.6 77.2 --start 2050-01-01 --end 2059-12-31
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import input_access as inputs  # noqa: E402
from data_access import (  # noqa: E402
    COARSE_ONLY_VARIABLES,
    GCMS,
    METHODS,
    PRODUCTS,
    VARIABLES,
    bbox_tag,
    check_nearest,
    coverage,
    describe_request,
    ensemble_member,
    load_downscaling_store,
    members_for,
    output_filename,
    point_tag,
    qa_flag_vars,
    variables_for,
)

# Written out rather than discovered, so `--help` never touches the network.
# argparse also cannot express "scenarios valid for the chosen GCM", so this is
# the union; the loader rejects an unavailable combination with a message
# naming what that GCM/method actually publishes.
ALL_SCENARIOS = ["g6_1p5k", "g6_1p5k_end", "historical", "ssp245"]

# The published products, plus the processed GCM input the pipeline started from.
CLI_PRODUCTS = PRODUCTS + ["input"]
INPUT_ONLY_VARIABLES = [v for v in inputs.VARIABLES if v not in VARIABLES]

# A request reading more than this prompts for confirmation. Downscaled chunks
# span about a year over a regional tile, so a global request reaches tens of GB
# very easily.
PROMPT_ABOVE_GB = 1.0


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="download.py",
        description="Download a spatial/temporal subset of the SRM downscaling dataset.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Examples")[-1],
    )
    p.add_argument("--scenario", required=True, choices=ALL_SCENARIOS)
    p.add_argument("--gcm", choices=GCMS, help="required")
    p.add_argument("--method", choices=METHODS,
                   help="downscaling method; required, except with --product input")
    p.add_argument(
        "--product", choices=CLI_PRODUCTS,
        help="required: downscaled (0.25 degree), debiased_coarse (bias-corrected on the "
             "GCM's native grid, before downscaling) or input (the GCM data before bias correction)",
    )
    p.add_argument(
        "--variable", choices=VARIABLES + COARSE_ONLY_VARIABLES + INPUT_ONLY_VARIABLES,
        help="required to download; dtr is available with --product debiased_coarse only, "
             "hurs with --product input only",
    )
    p.add_argument(
        "--member",
        help="ensemble member; required to download. Run --list-members to see which members "
             "a scenario contains and what each covers",
    )
    p.add_argument(
        "--list-members", action="store_true",
        help="list the members available for --scenario, with coverage, then exit",
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
        help="also write the quality flag variables. The per-day flag shares the data's "
             "chunk grid, so this roughly doubles the bytes read",
    )
    p.add_argument("--dry-run", action="store_true", help="report cost, download nothing")
    p.add_argument("--yes", "-y", action="store_true", help="skip the confirmation prompt")
    args = p.parse_args(argv)
    _check_product_args(args)
    return args


def _check_product_args(args) -> None:
    """Require every choice that identifies the data, and reject combinations that do not apply."""
    missing = []
    if args.gcm is None:
        missing.append(f"--gcm (one of: {', '.join(GCMS)})")
    if args.product is None:
        missing.append(f"--product (one of: {', '.join(CLI_PRODUCTS)})")
    if args.product != "input" and args.method is None:
        missing.append(f"--method (one of: {', '.join(METHODS)}; not used with --product input)")
    if not args.list_members and args.variable is None:
        missing.append("--variable (run --list-members to see what the scenario contains)")
    if missing:
        raise SystemExit("error: missing " + "; ".join(missing))

    if args.product == "input":
        if args.method is not None:
            raise SystemExit(
                "error: --method does not apply to --product input; the input stores hold the "
                "GCM data before any downscaling method was applied"
            )
        if args.qa_flags:
            raise SystemExit("error: the input stores carry no quality flags; drop --qa-flags")
        return
    if args.variable in INPUT_ONLY_VARIABLES:
        raise SystemExit(f"error: {args.variable} is available only with --product input")


def _address(args, *rest: str) -> str:
    """Where a request points, naming the product only when it is not the downscaled data."""
    if args.product == "input":
        return "/".join((args.gcm, "input", args.scenario, *rest))
    product = None if args.product == "downscaled" else args.product
    return "/".join(p for p in (args.gcm, args.method, product, args.scenario, *rest) if p)


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
        label = point_tag(*args.point)
    elif args.bbox:
        label = bbox_tag(*args.bbox)
    else:
        label = "global"
    suffix = ".zarr" if args.format == "zarr" else ".nc"
    if args.product == "input":
        return Path(
            inputs.output_filename(
                args.scenario, args.variable, args.start, args.end,
                gcm=args.gcm, member=member, label=label, suffix=suffix,
            )
        )
    return Path(
        output_filename(
            args.scenario, args.variable, args.start, args.end,
            gcm=args.gcm, method=args.method, member=member, product=args.product,
            label=label, suffix=suffix,
        )
    )


def list_input_members(args) -> int:
    """The input-store counterpart of list_members, from the chunk manifest (no data read)."""
    variables = inputs.variables_for(args.scenario, args.gcm)
    carried: dict[str, list[str]] = {}
    for variable in variables:
        for member in inputs.members_for(args.scenario, variable, args.gcm):
            carried.setdefault(member, []).append(variable)

    days = inputs.shard_days(args.scenario, variables[0], args.gcm)
    print(f"{_address(args)} (spans accurate to within {days} days, "
          "and --start/--end are checked exactly)")
    print(f"{'member':12s} {'coverage':25s} variables")
    for member in sorted(carried):
        first, last = inputs.coverage(args.scenario, carried[member][0], args.gcm, member)
        print(f"{member:12s} {first} to {last}  {' '.join(sorted(carried[member]))}")

    return 0


def list_members(args) -> int:
    """Print what a scenario contains: members, coverage, and variables each carries.

    Coverage is a property of the member, not the variable -- on CESM2-WACCM6
    ssp245, members 001-005 run to 2099 while 006-010 stop in 2069 and are the
    only ones carrying tasmax/tasmin -- so this is the table you need before
    choosing one.
    """
    variables = variables_for(args.scenario, args.gcm, args.method, product=args.product)
    carried: dict[str, list[str]] = {}
    for variable in variables:
        for member in members_for(args.scenario, variable, args.gcm, args.method, product=args.product):
            carried.setdefault(member, []).append(variable)

    print(_address(args))
    print(f"{'member':12s} {'coverage':25s} variables")
    for member in sorted(carried):
        first, last = coverage(
            args.scenario, carried[member][0], args.gcm, args.method,
            member=member, product=args.product,
        )
        print(f"{member:12s} {first} to {last}  {' '.join(sorted(carried[member]))}")

    return 0


TERMS_FILENAME = "TERMS_OF_DATA_ACCESS"
TERMS_SOURCE = Path(__file__).resolve().parents[1] / TERMS_FILENAME


def write_terms_beside(out: Path) -> Path | None:
    """Drop a copy of the Terms of Data Access next to a download.

    Zarr output is a directory, so the copy goes in at its top level; netCDF is a single file, so
    the copy sits beside it. Returns the path written, or None when this script runs without the
    repository alongside it and the canonical file is therefore missing.

    Parameters
    ----------
    out : Path
        The path just written by a download.

    Returns
    -------
    Path or None
        Where the terms were written, or None if the canonical file could not be found.
    """
    if not TERMS_SOURCE.is_file():
        return None
    target = (out if out.is_dir() else out.parent) / TERMS_FILENAME
    target.write_text(TERMS_SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def main(argv=None) -> int:
    args = parse_args(argv)

    try:
        if args.list_members:
            return list_input_members(args) if args.product == "input" else list_members(args)

        if args.product == "input":
            member = inputs.ensemble_member(args.scenario, args.variable, args.gcm, args.member)
            # The input time axis spans the whole scenario with NaN outside a member's
            # record, so read the real edges: about ten chunk reads.
            first, last = inputs.coverage(args.scenario, args.variable, args.gcm, member, exact=True)
            ds = inputs.load_input_store(args.scenario, args.variable, args.gcm, member)
        else:
            member = ensemble_member(
                args.scenario, args.variable, args.gcm, args.method, args.member,
                product=args.product,
            )
            ds = load_downscaling_store(
                args.scenario, args.variable, gcm=args.gcm, method=args.method,
                member=member, qa_flags=args.qa_flags, product=args.product,
            )
            # Read coverage off the axis we just opened rather than a transcribed table,
            # so it is always the member's own record.
            first, last = (str(ds.time.values[i])[:10] for i in (0, -1))
    except (ValueError, RuntimeError) as exc:
        hint = ""
        if args.member is None and not args.list_members and str(exc).startswith("no member given"):
            hint = "\nPass one with --member; --list-members shows what each covers."
        raise SystemExit(f"error: {exc}{hint}")

    validate_dates(args, member, first, last)

    print(f"{_address(args, args.variable)} -> member {member}")
    print(f"coverage: {first} to {last}")

    if args.start or args.end:
        ds = ds.sel(time=slice(args.start, args.end))
    if args.point:
        lat, lon = args.point
        try:
            # The data is global, so only a point off the grid (e.g. longitude 0-360) can miss.
            check_nearest(ds, lat=lat, lon=lon, check_data=False)
        except ValueError as exc:
            raise SystemExit(f"error: {exc}")
        ds = ds.sel(lat=lat, lon=lon, method="nearest")
    elif args.bbox:
        lon_min, lat_min, lon_max, lat_max = args.bbox
        ds = ds.sel(lat=slice(lat_min, lat_max), lon=slice(lon_min, lon_max))

    if ds[args.variable].size == 0:
        raise SystemExit("error: selection is empty; check the dates and region")

    read_bytes = describe_request(ds[args.variable], "requested subset")
    flags = qa_flag_vars(ds, args.variable)
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
    # 3-D chunk and shard grid of the group, so writing a reduced selection with
    # it raises an arity error in zarr.
    out_ds = ds
    for name in out_ds.variables:
        out_ds[name].encoding = {}

    if args.format == "zarr":
        # Zarr needs uniform chunks, and a date range rarely starts on a store chunk
        # boundary, so the selection's first and last dask chunks are ragged.
        out_ds.chunk("auto").to_zarr(out, mode="w")
    else:
        # NetCDF attrs cannot hold None, which the store uses for an unset
        # provenance field such as ssp245_ensemble_member.
        out_ds.attrs = {k: ("" if v is None else v) for k, v in out_ds.attrs.items()}
        out_ds.to_netcdf(out)

    size = sum(f.stat().st_size for f in out.rglob("*")) if out.is_dir() else out.stat().st_size
    print(f"wrote {out} ({_human(size)})")

    terms = write_terms_beside(out)
    if terms is not None:
        print(f"wrote {terms}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
