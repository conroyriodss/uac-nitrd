"""Vendor the local PubMedBERT encoder (workflow.embedding.LOCAL_PIN) into the model cache, once.

Not used by arm B v1, which uses the hosted endpoint (workflow.embedding.PIN); kept so the
biomedical, offline, weight-pinned alternative stays reproducible.

Downloads each file in workflow.embedding.FILES from the pinned commit revision (never a branch),
checks the weights against LOCAL_PIN["weights_sha256"] (the Hub's LFS hash), and writes VENDOR.json with
the SHA-256 of every file. The build then loads the encoder offline and re-checks every hash. This
step sends no award data.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workflow import embedding as em  # noqa: E402


def main() -> int:
    d = em.local_dir()
    if (d / "VENDOR.json").exists():
        em.verify_vendored()
        print(f"already vendored and verified: {d}")
        return 0
    d.mkdir(parents=True, exist_ok=True)
    for name in em.FILES:
        url = f"https://huggingface.co/{em.LOCAL_PIN['repo']}/resolve/{em.LOCAL_PIN['revision']}/{name}"
        dest = d / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
        tmp.rename(dest)
        print(f"{name}: {dest.stat().st_size} bytes", flush=True)
    files = {name: em.sha256_file(d / name) for name in em.FILES}
    if files[em.LOCAL_PIN["weights_file"]] != em.LOCAL_PIN["weights_sha256"]:
        raise SystemExit("downloaded weights do not match the pinned SHA-256; not vendored")
    vendor = {"repo": em.LOCAL_PIN["repo"], "revision": em.LOCAL_PIN["revision"], "files": files,
              "vendored_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
    (d / "VENDOR.json").write_text(json.dumps(vendor, indent=1, sort_keys=True) + "\n")
    em.verify_vendored()
    print(json.dumps(vendor, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
