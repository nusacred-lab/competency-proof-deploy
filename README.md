# Competency Proof Deployment

Run an independent instance of the Competency Proof credential demo using your
own domains and signing identity. This repository contains Docker Compose,
configuration preparation, environment checks, application build scripts and an
Android APK build script. It does not require access to the original demo's DNS,
certificates, accounts, keys or runtime data.

The flow uses real walt.id issuer, wallet and verifier services: issue a synthetic
competency credential, receive and store it in the wallet, then present it to an
employer for verification. The organizations are fictional. Use synthetic data.

## Prepare

You need:

- A Linux x86_64 host with a local Docker Engine and Compose v2. Plan for at least
  12 GiB available to Docker and 20 GiB free disk; leave additional build headroom.
- Python 3.10+, OpenSSL, Git, Node.js, JDK 21 and an Android SDK with platform
  `android-37.0` and Build Tools `37.0.0`. Set `JAVA_HOME`, `PATH` and `ANDROID_HOME`.
- Six reviewer-controlled DNS hostnames and a publicly trusted TLS certificate
  covering all six, with `fullchain.pem` and an unencrypted `privkey.pem` in a
  private directory. A wildcard certificate can cover hosts under one parent.
- HTTPS on public port 443 reachable from your browser and Android phone, either
  directly on the deployment host or through your own TLS-passthrough tunnel.
- An Android 11+ phone. Android 12+ is recommended for App Links diagnostics.

Builds may run on a separate Linux machine; follow [preparation details](docs/PREPARATION.md)
for tools, DNS/TLS routing and transferring images. Apple Silicon, Windows-native
Docker, private certificate authorities and automatic certificate issuance are
not supported by this guide.

## Configure and check

```sh
git clone https://github.com/nusacred-lab/competency-proof-deploy.git
cd competency-proof-deploy
cp config/reviewer.example.json config/reviewer.json
```

Edit `config/reviewer.json` with your six hostnames, private absolute runtime and
TLS paths, and listener ports. The configuration contains no passwords. The private
runtime must be outside this checkout and contain a directory named `runtime` in
its path. Configuration keys are explained in [preparation details](docs/PREPARATION.md).

```sh
python3 scripts/preflight.py --android --network
```

Fix each failed check before proceeding. DNS success does not establish that your
phone can reach the deployment; a public readiness check follows startup.

## Build and start

```sh
python3 scripts/deploy.py pull
python3 scripts/build.py init-signing
python3 scripts/build.py server
./scripts/build-android.sh
python3 scripts/deploy.py prepare
python3 scripts/deploy.py up
python3 scripts/deploy.py ready
```

The walt.id and supporting services use existing digest-pinned images. The three
application images must currently be rebuilt because the pinned application
baseline enforces its public domains in code. The build script applies your
configuration to an exact source commit and records the resulting file hashes.
Both application and APK builds use strict dependency verification. The first
build downloads dependencies and can take substantially longer than later builds.

The APK is signed with a newly generated **reviewer-owned demo key**. Keep this key
for updates. It uses package `id.nusacred.wallet.reviewer` so it can coexist with
the original wallet. Build results stay in your private runtime:

- `artifacts/competency-proof-reviewer.apk`: signed APK.
- `artifacts/SHA256SUMS` and `android-build.json`: checksum and signing record.
- `installation.json`: generated synthetic login accounts and private secrets.
- `server-build.json` and `reviewer-manifest.json`: exact local image selection.

Preparation publishes the APK certificate association through the wallet domain.
Install the APK only after public readiness passes:

```sh
adb install -r /absolute/private/runtime/competency-proof-reviewer/artifacts/competency-proof-reviewer.apk
adb shell pm verify-app-links --re-verify id.nusacred.wallet.reviewer
adb shell pm get-app-links id.nusacred.wallet.reviewer
```

Wait for Android verification and confirm your wallet host is `verified`. See
[troubleshooting](docs/TROUBLESHOOTING.md) if it is not. ADB is optional for manual
APK installation; its App Links diagnostics require Android 12+.

## Demonstrate the credential flow

Open the issuer, wallet-provider and employer domains from your configuration.
Use the generated `applicant`, `issuer-admin`, `custodian-admin` and `company-admin`
credentials in the private `installation.json` file. See the
[walkthrough](docs/WALKTHROUGH.md) for the full sequence and expected results.

You can additionally run `python3 scripts/check-flow.py` to exercise real issuance,
wallet read-back, presentation and positive/negative verification through the
public HTTPS applications. It creates synthetic records in this reviewer instance
and writes a private report. This is an API check, not evidence of Android UI use.

## Stop, restart and retain data

```sh
python3 scripts/deploy.py status
python3 scripts/deploy.py stop
python3 scripts/deploy.py up
```

Stop retains volumes and keys. Reuse the same runtime, project, configuration and
signing identity. Use a fresh runtime and project name when changing domains;
existing identity databases are not migrated automatically. Keep the generated
credentials, TLS private key, signing key and private reports out of source control.
See [data and cleanup](docs/PREPARATION.md#data-and-cleanup) before deleting anything.

## Scope and validation

This is a single-issuer, single-employer synthetic demo with a custodial Android
wallet. Real personal data, public self-registration, external SMTP, unattended
operations and production deployment are outside this package's scope. Mailpit
provides a private synthetic mailbox. Credentials and holder keys stay server-side.

See [validation status](docs/VALIDATION.md) for checks actually completed and
remaining environment/device validation. See [provenance](docs/PROVENANCE.md) for
source pins, local build changes and upstream image verification.

Application source: [competency-proof](https://github.com/nusacred-lab/competency-proof).
Infrastructure baseline: [platform-infra](https://github.com/nusacred-lab/platform-infra).
Credential services: [waltid-identity](https://github.com/nusacred-lab/waltid-identity).
Licensed under [Apache-2.0](LICENSE).
