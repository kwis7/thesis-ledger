# Private single-user hosting

Local operation is the verified release path. Hosted cloud deployment, reverse-proxy configuration and real email delivery have not been run for this release. The same API/workbench can be self-hosted after you configure and verify these boundaries.

## Local private desk

```sh
python3 run.py serve --workspace .thesisledger/workspace --host 127.0.0.1 --port 8765 --no-open
```

The default listener is loopback. Browser writes require the same origin and local Host header. Runtime research stays in the workspace you selected. Give each private user a separate process and workspace; multi-tenant authorization is not implemented.

## Cloud setup checklist

1. Copy the clean source files to a host you control. Keep runtime data outside the source/release tree and on a local filesystem with restricted permissions.
2. Put the service behind a TLS reverse proxy with your private identity/access control. Keep the Python process unreachable from the public internet. Restrict its listener with firewall/container/network policy.
3. Configure `THESISLEDGER_API_TOKEN` through your own environment/secret store. A non-loopback bind refuses to start without this token. The Python service cannot verify that a TLS proxy exists; token presence alone is not a safe deployment.
4. Run the loopback service with `--public-origin https://desk.your-domain.example` set to your exact private browser origin. This option requires an API token and HTTPS. Preserve the proxy's upstream Host as `127.0.0.1:8765`. The app then permits that explicitly configured browser origin without trusting arbitrary forwarded headers. Test `/api/health`, authenticated access and writes through your actual proxy. Do not disable validation to make an incorrect proxy setup work.
5. Test a synthetic workspace first. Verify access denial from an unauthenticated browser, no direct network exposure, restart recovery and event intake. Then import only your public/redacted packets.
6. Use a service supervisor for `serve` and, separately, your event collector/`monitor`. Document the cadence, source failure policy and source-specific usage/data rights. No automation is created by opening the UI.

The browser asks for a workbench token only when the API requires it and retains it in page memory. It does not place the token in a URL, local storage or the published examples.

## Backup and recovery

Use SQLite's backup API or stop your own service before taking a filesystem backup. In WAL mode, copying only the main `.sqlite3` file while writes continue can miss committed data. Restore into a new workspace and inspect counts, revisions and outbox states before resuming your worker. Never automatically requeue an ambiguous send.

## Optional email

Email preview needs no account. In a sourced workspace, `email_enabled` allows new eligible material alerts to enter an outbox subject to cooldown. It does not send them. Set SMTP host, port, user, password and recipient using environment variables named `THESISLEDGER_SMTP_HOST`, `_PORT`, `_USER`, `_PASSWORD`, `_RECIPIENT`. Keep secrets in your git-ignored project `.env` or secret manager; the CLI reads inherited environment variables and does not automatically source a file.

After inspecting your queued alerts and authorizing real sending, the operator can run:

```sh
python3 run.py deliver --workspace .thesisledger/workspace --confirm-send --limit 5
```

The worker checks mode, pause, quiet hours and event age before claiming an attempt. It only uses implicit TLS SMTP (`SMTP_SSL`). `provider_accepted` means the relay accepted the message, not that a recipient's inbox received it. `failed` and `unknown` are not automatically retried. Synthetic demo mode never queues or sends external email.

An interrupted attempt stays `in_flight` until the operator investigates the provider outcome. `reconcile --before TIMESTAMP` marks abandoned attempts unknown and never requeues them. This explicit step avoids duplicate messages after a timeout or restart. Real SMTP acceptance and end-to-end inbox delivery remain unverified here.
