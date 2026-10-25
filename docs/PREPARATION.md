# Deployment preparation

## Choose the topology

The simplest supported topology is one Linux x86_64 machine that both builds and
runs the demo. Allocate at least 12 GiB of memory to Docker and 20 GiB free disk,
plus headroom for Gradle, Android tools and the host. These are starting requirements,
not a performance guarantee. Do not run a second complete stack beside an active
demo on an undersized host.

For a separate build machine, generate source, signing identity, APK and images
there. Transfer the three application images with `docker save` / `docker load`,
and transfer the private runtime with its configuration, build records, signing
identity and artifacts through an encrypted channel. Keep the configured absolute
runtime path the same on both machines. Install the TLS files at the configured
private path on the runtime host, then run `pull`, `prepare` and `up` there.
Do not start the same project from two machines sharing mutable state.

## Hostname and HTTPS routing

Configure six distinct names under a domain you control. For example, if your
zone is `credentials.your-domain.tld`, use:

| Configuration key | Example prefix | Purpose |
| --- | --- | --- |
| `domains.wallet` | `wallet` | Wallet portal, native API and App Links |
| `domains.issuer` | `issuer` | Issuer portal and public issuer profile |
| `domains.employer` | `employer` | Employer portal and public job page |
| `domains.wallet_auth` | `login-wallet` | Participant and wallet-administrator login |
| `domains.issuer_auth` | `login-issuer` | Issuer staff login |
| `domains.employer_auth` | `login-employer` | Employer staff login |

All six names must reach this installation on external HTTPS port 443. A wildcard
DNS record and wildcard certificate can cover six sibling names. You are responsible
for DNS ownership and certificate issuance/renewal; this package does not use the
original operator's domain or tunnel account.

Two routing options are supported:

- **Direct host:** set `https_bind_address` to `0.0.0.0` and `https_port` to `443`.
  Point DNS to that host and permit inbound TCP 443. Ensure no other server owns it.
- **TLS-passthrough tunnel:** bind to `127.0.0.1` on an available high port, for
  example `29443`. Configure your own tunnel to forward all six external hostnames
  on port 443 to that listener, preserving TLS and SNI. Start and maintain the
  tunnel separately. TLS termination in an unrelated proxy is not covered here.

Private identity administration and the synthetic mailbox always bind to loopback.
Do not forward their ports, databases or credential-protocol diagnostics publicly.
If DNS publishes IPv6, route it correctly too or remove the unusable AAAA record.

`tls_directory` must contain a matching publicly trusted `fullchain.pem` and
unencrypted `privkey.pem`. Preparation copies them into the runtime and creates
the Java truststore. Keep the parent private (0700); files are container-readable
only within that private runtime. The preparer requires a certificate covering all
six names, at least 24 hours remaining, and a chain trusted by the host OpenSSL CA
store. The public readiness check verifies normal DNS and system TLS trust.

This is not an automatic TLS renewal system. Before the certificate expires, stop
the reviewer stack and replace the retained runtime's TLS certificate/key and Java
truststore consistently, or create a fresh reviewer installation. Do not merely
renew a source file and assume existing runtime copies changed.

## Build tools

Install a JDK 21 distribution, Git, Python 3.10+, Node.js, OpenSSL, Docker Engine
and Docker Compose v2. Put JDK 21's `bin` directory first in `PATH` and set
`JAVA_HOME`. Set `ANDROID_HOME` to the Android SDK directory.

With Android command-line tools installed, provision the required packages:

```sh
sdkmanager "platforms;android-37.0" "build-tools;37.0.0" "platform-tools"
sdkmanager --licenses
```

Review the license terms before accepting. The repository does not auto-accept
licenses. `adb` comes from platform-tools. The Gradle wrapper downloads its pinned
Gradle distribution. Gradle also downloads reviewed project dependencies and
WebAssembly build tooling, so builds need outbound network access.

For optional upstream image-attestation verification, also install GitHub CLI and
Cosign 3.1.3, authenticate to GitHub and run:

```sh
python3 scripts/deploy.py verify-images
```

The inherited verification checks only upstream images. Newly built application
images are recorded locally; they do not inherit upstream CI attestations.

## Configuration reference

Copy `config/reviewer.example.json` to the ignored `config/reviewer.json`.
An alternative file can be passed using `--config /absolute/path/config.json` to
all commands, including the Android shell wrapper.

| Key | Meaning |
| --- | --- |
| `project` | `competency-proof-reviewer` or that prefix plus a distinct suffix; scopes Docker volumes/networks |
| `runtime_directory` | New canonical absolute path outside the checkout, without spaces; must contain a `runtime` directory component |
| `domains` | The six exact lowercase DNS hostnames above; no scheme, port or path |
| `https_bind_address` | Local IPv4 bind address, usually `0.0.0.0` or `127.0.0.1` |
| `https_port` | Local public-edge listener; external URLs always use port 443 |
| `admin_port` | Unused local port for private identity administration, loopback only |
| `mailbox_port` | Unused local port for synthetic mailbox access, loopback only |
| `tls_directory` | Absolute private directory containing the reviewer certificate and key |
| `minimum_memory_gib` | Docker memory check, at least 12 GiB |
| `minimum_disk_gib` | Runtime disk check, at least 20 GiB |

The configuration has no credentials, but it may identify your environment, so it
is ignored by Git. All passwords and issuer keys are generated privately. No real
personal information is needed for credentials. Generated login emails end in
`example.test`; Mailpit captures their mail privately, without external SMTP.

The preparer binds a runtime to its complete configuration. Changed domains, ports
or project names require a fresh runtime and a distinct project name. This avoids
silently applying new URLs to an identity database imported under old URLs.

## Data and cleanup

The prepared installation includes persistent identity databases, wallet/holder
keys, credentials, business records, source/build records and reviewer APK signing
keys. `stop` retains them. Back up the private runtime and all project volumes
consistently if you need to preserve the installation. Recreating only the runtime
or only the volumes is not a recovery procedure.

For final disposal, first stop the exact reviewer project. Inspect project labels
and use the prepared Compose environment to remove **only that reviewer's** project
and its volumes. Runtime files, APK signing identity and copied TLS keys need
separate deliberate removal. No automatic deletion command is provided; never use
broad Docker pruning or remove the original demo's data to clean up this instance.
