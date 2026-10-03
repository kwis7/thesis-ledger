# Source access and alternatives

The workbench starts with an attributed offline EXE case. Network checks are separate operator-started commands, with no silent provider switch. For step-by-step application declaration and a one-shot access check, use the [user guide](USER_GUIDE.md#declare-your-application-to-sec) ([中文](USER_GUIDE.zh-CN.md#sec-setup)).

| Route | Fetches | What it establishes |
| --- | --- | --- |
| `sec-watch EXE` | One official SEC submissions JSON GET | Latest eligible periodic filing in the recent metadata window; contents still need review |
| `ir-watch EXE` | Official EXE robots policy, then first annual and quarterly listing pages | Issuer-listed date, form, accession and report link; report period and financial contents remain unmapped |
| `sec 0000895126` | SEC submissions and companyfacts JSON, two sequential GETs | Hashed source snapshots and explicitly selected facts; it does not accept a new model baseline |

For both monitor commands, keep the same `--workspace` as the running EXE workbench. Standalone `sec` stores snapshots in its `--cache-dir` and does not use `--workspace`. Without `--once`, monitors check every 15 minutes while their processes remain running. These commands do not install a scheduler or send email.

## If SEC returns 403

The observed refusal at 2026-10-03 04:28 UTC included **Undeclared Automated Tool**. This classifies the response; it does not identify a unique root cause. SEC guidance asks automated applications to declare their identity and contact information. Supply a real public project contact in `--user-agent '<app-name/version public-contact>'`. The collector does not save this contact or the refusal body. See [SEC access guidance](https://www.sec.gov/about/webmaster-frequently-asked-questions) and the [official API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).

A refusal stops the process. Review the identity/contact and network access before explicitly restarting. Do not invent an email, impersonate a browser, rotate identities or proxies, or repeatedly retry a refusal. For unresolved access, the SEC guidance provides a webmaster support route; contacting support is the operator's choice.

## Use the official company site

```sh
python3 run.py ir-watch EXE --once
```

The alternative uses a truthful application identifier and public project-owner link. It follows the official site's robots policy, waits at least one second between requests, limits each response to 2 MiB, refuses redirects and saves hashed raw snapshots within a 64 MiB cache budget. Invalid issuer identity, table structure, dates or links stop collection. It does not fetch full report documents or bypass SEC access.

One live check found accession `0000895126-26-000047`, a 10-Q listed as filed July 28, 2026, and created one local review alert. The packaged [minimal excerpts](../examples/ir/README.md) support offline parser tests; they are not full current listings. Inspect the [official EXE listing](https://investors.expandenergy.com/financial-information/sec-filings) if the adapter reports a structure change.

**Monitor & timeline** shows company-site and SEC status separately. A successful company-site check does not clear SEC failure or mark financial inputs fresh. The reporting period is explicitly unknown, and model assumptions and history remain unchanged. Verified official discoveries share accession-based deduplication; an unverified mention cannot suppress a subsequent verified discovery.

The issuer route is currently EXE-specific. Adding another company requires an explicit adapter with grounded URLs and equivalent validation. Neither route provides exhaustive filing history, live quotes or automatic financial-model updates.

## If both live routes are unavailable

The packaged case still runs offline with `python3 run.py case EXE`. Prepare a reviewed public company packet using the [input contract](DATA_CONTRACT.md), then propose it with `baseline` and accept the exact candidate in the workbench. Label its actual source and acquisition time. Saved public inputs can continue to support scenario calculations and run replay; their age remains visible.
