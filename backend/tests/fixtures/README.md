These fixtures are project-authored development probes copied byte for byte
from `knowledge/evidence/creatine-clarity-v1/questions.jsonl` and
`knowledge/evidence/safety-boundary-round2/{questions.jsonl,manifest.json,first-use.json}`.
The boundary manifest retains its original question hash and historical outcome.
They let safety regressions run from a fresh checkout without publisher documents
or unpublished local research artifacts. They are development regressions, not an
independent clinical evaluation. Keep the original evidence snapshots unchanged.

`active-card-text-hashes.json` records canonical UTF-8/LF hashes derived from
the original cards after verifying their recorded raw-byte hashes. It permits
Git's text newline conversion without weakening the check on card contents or
changing the historical evidence manifest. `.gitattributes` preserves the exact
bytes of the frozen boundary question file because its raw hash is asserted.
