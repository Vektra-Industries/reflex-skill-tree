# Contributing

RSTP is a protocol + a reference implementation. Contributions welcome in
both directions:

- **Protocol changes** (new fields, tier semantics, promotion rules): open an
  issue first — changes to meaning (not additions) require a version bump
  per SPEC.md §8.
- **Implementation bugs/improvements**: PR directly against `rstp/`. Keep it
  stdlib-only; that's a deliberate design constraint, not an oversight.
- **New-language implementations**: link them from README once they pass the
  conformance behavior described in SPEC.md (cycle rejection, promotion/
  demotion thresholds, tier semantics).

Run the tests before opening a PR:

```bash
python3 -m unittest discover -s tests -v
```
