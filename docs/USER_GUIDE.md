# User guide

[中文](USER_GUIDE.zh-CN.md) · [README](../README.md)

Start with the offline case. Activate a public-source monitor after you have seen the research loop. The interface uses English; this guide uses its button names.

## Open a first workspace

Download and extract the repository, or clone it. Open a terminal in the folder containing `run.py`. With Python 3.10 or newer installed, run:

```sh
python3 run.py case EXE
```

Visit `http://127.0.0.1:8765/#lab` if the browser does not open. The command stays running while you use the workbench. No SEC request, external model call or email send is needed for this case.

Your data is saved under `.thesisledger/exe-case/`. Press Ctrl+C to stop; rerun the same command to resume. To keep another case separate or avoid a used port:

```sh
python3 run.py case EXE --workspace .thesisledger/exe-second --port 8766
```

Every monitor must use the same workspace path as the case it follows. The monitor's default is `.thesisledger/exe-case`; it will not find a case stored somewhere else unless you pass that path.

## Complete one research loop

1. Open **Research Lab**. Inspect the source facts and their fiscal periods.
2. Change **Realized price** from 3.5 to 4.0 USD/Mcfe. Follow the cash-flow bridge. This is an assumption scenario; the accepted baseline stays unchanged.
3. Click **Run evidence review**. Read the three source-linked suggestions and tool results. The default planner is deterministic and offline.
4. Click **Verify saved run** to replay the captured decisions and compare hashes. Matching code is required to reproduce an older run.

Opening a source or marking an alert reviewed records your attention. Accepting revised assumptions or a full candidate baseline is a separate action that creates a model revision. A new filing alert alone cannot update the financial model.

## Add EXE company-site monitoring

Keep the case running. Open a second terminal in the same repository and run:

```sh
python3 run.py ir-watch EXE --workspace .thesisledger/exe-case --once
```

This performs one bounded check of EXE's official filing lists after checking the site's robots policy. Open **Monitor & Timeline** or **Alerts** and click **Refresh saved workspace**. The page displays the company-site status, last attempt and any new review alert. A result with zero new alerts can be normal when the filing was already known.

The adapter is EXE-specific. It discovers listing dates, forms, accessions and report links. It does not establish report periods or extract new financial figures. Use the linked document for a financial review before proposing a model change. A successful company-site check does not clear a separate SEC failure or mark old financial inputs fresh.

## Declare your application to SEC

SEC's public `data.sec.gov` APIs need no authentication or API key. Automated callers declare an application identity and contact in the HTTP `User-Agent` header. This is not account verification or a document-based identity check. See the [official API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) and [SEC's declared-bot guidance](https://www.sec.gov/about/webmaster-frequently-asked-questions).

### 1. Prepare a truthful declaration

Use the application name/version, your actual operator or organization name, and a contact email you control and are willing to send to SEC. A project email can be used; keep it reachable. Do not put a password, API key, account number or identity document in the header.

The following is a **template, not a ready-to-run command**. Replace both `<YOUR_REAL_OPERATOR_NAME>` and `<YOUR_REAL_CONTACT_EMAIL>`, then remove the angle brackets. Keep the complete declaration inside one pair of quotes. The quoted email will be transmitted to SEC; it does not have to be added to the public repository. Shell history and process listings may retain the command locally.

```sh
python3 run.py sec-watch EXE --workspace .thesisledger/exe-case --user-agent 'ThesisLedger/0.2.2 <YOUR_REAL_OPERATOR_NAME> <YOUR_REAL_CONTACT_EMAIL>' --once
```

ThesisLedger passes this string as the request header and does not save it in its source snapshots or workspace status. The CLI checks that the string is usable; it does not verify your email or register you with SEC. A truthful declaration does not guarantee that every network can access the endpoint.

### 2. Check one request before starting a loop

Run the replaced command with `--once`. It makes one GET for EXE submissions metadata. Refresh **Monitor & Timeline** and inspect **SEC direct**, its latest attempt and result.

| Result | What to do |
| --- | --- |
| `processed` | Inspect the new local filing-review alert and its source; financial mapping still needs review |
| `unchanged` | The latest eligible filing was already known or did not advance the case; zero new alerts is expected |
| `paused` | Resume monitoring in the workbench, then perform another deliberate one-shot check |
| `data_gap` | No eligible periodic filing was found in the bounded window; inspect the source gap before interpreting it |
| HTTP 403 / `Undeclared Automated Tool` | Stop and review the declaration and access guidance; do not treat the error page as a filing |
| Network or timeout error | No validated result is available; distinguish the transport failure from an HTTP refusal |

A successful run checks filing metadata. It does not mean the SEC authenticated your identity, certified the application or verified a financial model.

### 3. If access remains refused

Check that you replaced the template, kept the whole header in quotes and used a reachable contact. After resolving a concrete configuration issue, explicitly start another one-shot check. Avoid repeated retries or identity/proxy rotation.

For an unresolved Access Denied response, SEC's [FAQ](https://www.sec.gov/about/webmaster-frequently-asked-questions) provides `webmaster@sec.gov` as a support contact and asks for the error and public IP. If you choose to contact them, review what you send yourself. ThesisLedger does not email support, determine your public IP or upload diagnostics.

You can continue the offline case or explicitly choose `ir-watch EXE` while SEC access is unresolved. The two source statuses remain separate. Current project evidence includes one successful live issuer-site check; SEC direct recovery and continuous availability remain unverified. See [verification](VERIFICATION.md).

## Keep monitoring and pause it

After a successful one-shot check, remove `--once` from your chosen monitor command to check every 15 minutes while that terminal process runs. Keep the replaced SEC declaration if you use `sec-watch`. This does not install a scheduled service.

For the company-site route:

```sh
python3 run.py ir-watch EXE --workspace .thesisledger/exe-case
```

Use **Pause monitoring** in **Monitor & Timeline** to stop new collector calls. An already-started check may finish, including its remaining requests; pause does not cancel that check. A running process stays paused until you resume it. If a source check fails, its process exits and one local outage alert is retained. Resolve the issue and explicitly restart; clicking Resume cannot restart an exited terminal process.

Repeated verified discoveries share accession-based deduplication across sources. Repeated failures in one continuous outage do not produce additional outage alerts. Refreshing the saved workspace retains the sandbox and selected run while the accepted baseline is unchanged. Alerts appear locally; email preview does not send a message.

## Bring your own research

Prepare a public or deliberately redacted company JSON packet using the [input contract](DATA_CONTRACT.md), with explicit source dates, units, assumptions and gaps. `my-company.json` below is the path to the packet you prepared, not a supplied sample. Use a new workspace and keep it consistent:

```sh
python3 run.py init --workspace .thesisledger/my-research
python3 run.py import my-company.json --workspace .thesisledger/my-research
python3 run.py serve --workspace .thesisledger/my-research --port 8766
```

Import adds a company; it does not overwrite one already present. For a complete update, prepare a reviewed packet and propose it with `baseline FILE --workspace PATH`; inspect and accept the exact candidate in the workbench. A source alert contains metadata, not a ready-to-accept financial packet.

Use the [Agent starting prompt](../agents/START_HERE.md) for help preparing inputs. The built-in model contract supports industrial, recurring-customer and bounded commodity businesses. It does not automatically build complete models for arbitrary tickers; new live issuer adapters also require explicit implementation.

The [invented-company walkthrough](QUICKSTART.md) provides practice with conflicts and source outages. [Agent runtime](AGENT_RUNTIME.md) explains optional hosted inference. [Self-hosting](SELF_HOSTING.md) covers private cloud configuration and optional email. These advanced routes have separate configuration and verification limits; neither is required for the local case.
