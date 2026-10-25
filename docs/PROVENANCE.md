# Source and build provenance

This repository is licensed under Apache-2.0. It adapts the following files from
`nusacred-lab/platform-infra` at commit
`db19ce5519911e13f0a6aee51c40c1fe9345eaf0`, also licensed under Apache-2.0:

- `release/compose.yaml` → `compose.yaml`
- `release/install.py` → `scripts/engine.py`
- `release/prepare_protocol.py` → `scripts/prepare_protocol.py`
- `release/assets/` → `assets/`
- `release/acceptance.py` → `scripts/check-flow.py`
- `release/acceptance_transport.py` → `scripts/acceptance_transport.py`
- `release/current.json` → `baseline/release-manifest.json`

The original copyright and license terms are retained in LICENSE. Adaptations
configure reviewer hostnames, isolated runtime and ports, local application image
identities, empty template redirects populated during preparation, reviewer APK associations and the configuration-bound flow check.
Mail delivery adds an optional private Compose overlay and supports Mailpit or
authenticated SMTP with approved login inboxes; it does not change dependencies.
Existing realm/client identifiers and internal protocol URLs are retained because
they are protocol compatibility identifiers, not references to operator DNS.

## Application source adaptation

`sources.lock.json` pins the application at commit
`66948a755870f178e04138a916ca1ed2f5ddaba4`. `scripts/build.py` clones that exact commit,
verifies the wrapper checksum, and replaces the six original public hostnames in
tracked Kotlin, Gradle, XML and JavaScript sources with reviewer hostnames. It also
binds the legacy wallet alias to the reviewer wallet and changes the APK application
ID to `id.nusacred.wallet.reviewer`, allowing installation alongside the original app.
No dependency lock or verification hash is changed.

The adapted source stays in the private runtime. `source-record.json` records each
changed file's SHA-256 and the configuration hash. Repeated builds reject unrecorded
tracked changes or untracked source files. Server compilation runs the inherited
JVM, API and dependency checks before building three domain-specific application
images. The signed APK has its own checksum and certificate record.

## Image identity

The eleven upstream baseline images are pinned by registry digest. The command
`python3 scripts/deploy.py verify-images` verifies the upstream manifest attestation,
image signatures, provenance and SBOM attestations with GitHub CLI and Cosign 3.1.3.
It requires GitHub authentication for attestation retrieval and network access.

The three domain-specific application images are rebuilt locally and selected by
immutable local image ID. They are **not** covered by the original CI attestation
or image vulnerability scan. `reviewer-manifest.json` explicitly records this
local derivation and retains the upstream source records. It is not a signed
release manifest. Perform an additional image scan if your environment requires it.

Application compilation needs dependency downloads; pinning does not make the first
build offline. This repository does not publish reviewer signing keys or TLS keys.
