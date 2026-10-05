"""Freeze current card hashes without altering earlier version receipts."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--version", required=True)
parser.add_argument("--previous", required=True)
args = parser.parse_args()
assert all(v.startswith("v") and v[1:].isdigit() for v in [args.version, args.previous])
directory = ROOT / "knowledge/evidence" / ("content-fixes-" + args.version)
target = directory / "manifest.json"
assert not target.exists(), "Never overwrite a frozen manifest"
previous = ROOT / "knowledge/evidence" / ("content-fixes-" + args.previous) / "manifest.json"
old = {r["card"]: r["candidate_sha256"] for r in json.loads(previous.read_text(encoding="utf8"))["cards"]}
cards = []
for path in sorted((ROOT / "knowledge/cards").glob("*.md")):
    if path.name.startswith("_"):
        continue
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    cards.append({"card": path.stem, "previous_sha256": old[path.stem], "candidate_sha256": sha, "changed": old[path.stem] != sha})
directory.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps({"version": args.version, "previous": previous.relative_to(ROOT).as_posix(), "cards": cards,
                              "independent_review": "pending", "reason": "Fixes discovered in frozen release-v7 fresh evaluation; that evaluation is now development evidence."}, indent=2), encoding="utf8")
print(json.dumps({"version": args.version, "changed": [r["card"] for r in cards if r["changed"]]}))
