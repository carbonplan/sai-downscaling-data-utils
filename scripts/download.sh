#!/usr/bin/env bash
#
# Bash entry point for downloading a subset of the SRM downscaling dataset.
# Thin wrapper around scripts/download.py -- see `download.sh --help`.
#
# `pixi run download` does exactly the same thing and needs no bash, so it also
# works on Windows. Both take the same options.
#
# Examples
# --------
#   # Estimate what a request costs, without downloading anything:
#   ./scripts/download.sh --scenario ssp245 --gcm CESM2-WACCM6 --method bcsd \
#       --product downscaled --variable tas --member 003 \
#       --start 2050-01-01 --end 2059-12-31 --bbox 68 6 98 38 --dry-run
#
#   # Download a single-point time series to a NetCDF file:
#   ./scripts/download.sh --scenario historical --gcm CESM2-WACCM6 --method bcsd \
#       --product downscaled --variable tas --member r3i1p1f1 \
#       --point 28.6 77.2 --start 1990-01-01 --end 1999-12-31 --output delhi.nc
#
# Requests reading more than 1 GB prompt for confirmation; pass --yes to skip.

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(dirname "$here")"

cd "$repo"
exec pixi run python "$here/download.py" "$@"
