# PolicyManual

This folder contains tooling to download board policy text from:
https://www.bpcsd.org/board-of-education/board-policies

## Files
- `download_policies.py` - crawls the board policies index, opens each policy page, extracts the policy body, and writes one `.txt` file per policy.
- `policies_index.csv` - generated index of discovered policy titles and URLs.

## Run
python3 download_policies.py

Output is written to `PolicyManual/text/`.
