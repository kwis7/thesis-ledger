# Official EXE filing-list excerpts

These small, manually selected HTML excerpts preserve the official listing's date, form, accession link and table attributes for deterministic parser tests. They are attributed to [Expand Energy's investor website](https://investors.expandenergy.com/financial-information/sec-filings). Branding, scripts, document contents and unrelated page text are omitted.

- `annual-excerpt.html` includes annual filings, an amendment and an ARS row that must not become a periodic-filing alert.
- `quarterly-excerpt.html` includes three quarterly filing rows, including accession `0000895126-26-000047`.
- `provenance.json` records URLs, acquisition timestamps and hashes of the full responses captured at 2026-10-03 04:30 UTC. Those hashes belong to the original responses, not these edited excerpts. Full captures are excluded from this public source bundle.

The issuer listing does not establish the reporting period or financial figures. `reportDate` remains null. A conservative next Eastern midnight rule handles date-only availability, while actual acquisition time stays separate. These historical excerpts do not claim current listing completeness or source redistribution rights.

Run the offline checks from the checkout:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -p test_issuer_ir.py
```
