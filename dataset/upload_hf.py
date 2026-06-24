#!/usr/bin/env python3
"""Upload the dataset to HuggingFace. Reads the token from the HF_TOKEN env var
(never hard-coded). Uploads the parquet tables (for the Hub viewer) + the SQLite
bundle (for the honest-backtest loader) + the dataset card.

    HF_TOKEN=hf_xxx python dataset/upload_hf.py \
        --repo <user>/polymarket-updown-microstructure \
        --parquet /root/open_dataset_parquet \
        --sqlite /root/open_dataset.sqlite \
        --card /root/hf_readme.md

Run it yourself (e.g. `! HF_TOKEN=... python dataset/upload_hf.py ...`) so the
token stays in your environment. Use a FRESH write token and revoke it after.
"""
from __future__ import annotations

import argparse
import os
import sys


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="<user>/<dataset-name>")
    ap.add_argument("--parquet", default="/root/open_dataset_parquet")
    ap.add_argument("--sqlite", default="/root/open_dataset.sqlite")
    ap.add_argument("--card", default="/root/hf_readme.md")
    ap.add_argument("--no-sqlite", action="store_true",
                    help="skip the 2GB sqlite (upload parquet + card only)")
    a = ap.parse_args(argv)

    token = os.environ.get("HF_TOKEN")
    if not token:
        print("ERROR: set HF_TOKEN env var (a fresh write token).", file=sys.stderr)
        return 2

    from huggingface_hub import HfApi
    api = HfApi(token=token)
    api.create_repo(a.repo, repo_type="dataset", exist_ok=True)

    if a.card and os.path.exists(a.card):
        api.upload_file(path_or_fileobj=a.card, path_in_repo="README.md",
                        repo_id=a.repo, repo_type="dataset")
        print("uploaded README.md (card)")

    if os.path.isdir(a.parquet):
        api.upload_folder(folder_path=a.parquet, path_in_repo="parquet",
                          repo_id=a.repo, repo_type="dataset")
        print(f"uploaded parquet/ from {a.parquet}")

    if not a.no_sqlite and os.path.exists(a.sqlite):
        api.upload_file(path_or_fileobj=a.sqlite, path_in_repo="open_dataset.sqlite",
                        repo_id=a.repo, repo_type="dataset")
        print("uploaded open_dataset.sqlite")

    print(f"done → https://huggingface.co/datasets/{a.repo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
