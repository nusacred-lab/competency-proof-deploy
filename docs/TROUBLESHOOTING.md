# Troubleshooting

## Preflight fails

Read each `FAIL` line. Common causes are missing Docker socket access, a remote
Docker context, the wrong JDK, an incomplete SDK, occupied ports, insufficient disk,
example domains left in the configuration, and a TLS certificate missing one of
the login hostnames. No container is started by preflight. For an existing running
installation, add `--running` to skip unused-port checks.

## Build fails

Check JDK 21 is first in PATH and `ANDROID_HOME` contains platform `android-37.0`
and Build Tools `37.0.0`. Accept the SDK licenses yourself. The first build needs
GitHub, Gradle, Maven/Google dependencies and WebAssembly tooling to be reachable.
Do not disable strict dependency verification or change reviewed hashes to make a
failed download pass. Preserve the error and retry once connectivity is repaired.

The source is pinned and adapted in the private runtime. A changed configuration
or unrecorded source edit is rejected. Do not point the build at the active demo's
runtime. Use a new reviewer runtime/project when choosing different domains.

## Containers start but browser/phone login fails

Run `python3 scripts/deploy.py status`, followed by `ready`. Confirm all six public
hostnames reach the reviewer host on port 443, not the original demo. Inspect DNS,
firewall and tunnel mapping, including IPv6. URLs with `:29443` are not replacements
for the configured external HTTPS origins. Origin and callback checks are exact.

The initial Keycloak import applies only to an empty identity database. Changing
JSON import files does not migrate an existing realm. Use a fresh project/runtime
instead of reusing old volumes with new domains.

## Android opens the browser instead of the wallet

Confirm the reviewer APK is installed and your wallet host serves its generated
`/.well-known/assetlinks.json` without redirects over publicly trusted HTTPS.
The package must be `id.nusacred.wallet.reviewer`, and the certificate fingerprint
must match `android-build.json`. Re-run Android 12+ diagnostics:

```sh
adb shell pm verify-app-links --re-verify id.nusacred.wallet.reviewer
adb shell pm get-app-links id.nusacred.wallet.reviewer
```

Wait a few minutes for asynchronous verification. A `verified` hostname is the
expected result. Do not force approval and count it as successful verification.
See [Android's App Links verification guide](https://developer.android.com/training/app-links/verify-applinks).

## APK update is rejected

Retain the reviewer signing key. An APK signed with a different key cannot update
the installed app. This package deliberately uses a different application ID from
the original wallet. Do not delete or replace the operator's signing key.
APK signing and verification follow [Android's apksigner documentation](https://developer.android.com/tools/apksigner).

## Flow check fails

Its report is private and may contain test/account references. First check public
readiness and identity availability. A dependency failure is not proof of an
invalid credential. Do not blindly resubmit an issuance/presentation after an
ambiguous result; inspect the operation status before retrying.

When asking the maintainer for help, share the deployment repository commit,
host OS/architecture, failed command and a sanitized error. Never send passwords,
private keys, tokens, complete runtime configuration or an unredacted HAR/log dump.
Independent reproduction on another person's environment remains subject to the
validation status documented in this repository.
