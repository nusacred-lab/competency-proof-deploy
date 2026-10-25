# Validation status

This package is intended for an independent reviewer installation. Validation
results below apply to the deployment repository and its adapted application
builds; they do not inherit full acceptance from the original public demo.

The existing demo reached its own acceptance milestones, but that does not prove
that another reviewer can reproduce this configurable package without assistance.

## Completed checks

On 25 October 2026, the following checks passed on a Linux x86_64 build host:

- Fourteen deployment regression tests: domain validation, private-runtime binding,
  generated routing, source/image consistency, environment isolation and APK signer
  parsing, including rejection of malformed/multiple-signer output.
- Python syntax, local documentation links, workflow pins and private-file policy.
- Source retrieval at the exact pinned application commit, wrapper checksum and
  recorded adaptation of nine source/test files to six reviewer hostnames.
- Strict dependency verification: 1,322 reviewed artifact hashes and nine lockfiles.
- The inherited API contract check covering 39 operations and the portal loading
  checks for all three organizations.
- Seventy inherited JVM/API tests, three backend distributions and the production
  WebAssembly portal build.
- Three domain-specific Linux amd64 application image builds, recorded by local
  image ID.
- Android release compilation and lint, APK alignment, signing with a disposable
  reviewer-owned key and signature verification. The APK package was confirmed as
  `id.nusacred.wallet.reviewer` with minimum Android API 30.
- Compose configuration parsing and Caddy validation of the generated public and
  private routing in isolated validators with no public network or bound ports.
- Private-state preparation with a disposable test certificate, generated issuer
  keys, exact realm callbacks, local image bindings and matching APK association.
  No application/identity/protocol stack was started for this preparation check.
- Preflight rejection of the self-signed test certificate. That fixture is for
  configuration validation only and is not an accepted deployment certificate.

The source retrieval check used a local mirror of the pinned public application
repository. These are local build/validation results, not independent reviewer
acceptance or a new vulnerability scan of the derived application images.

## Mail configuration update

On 25 October 2026, all 27 deployment/mail tests passed, including actual Compose
resolution for both modes. Private-state preparation with disposable local inputs
also passed for both modes and all three realm SMTP/account bindings, without
starting either stack or connecting to a provider.

The selectable mail adapter adds regression coverage for Mailpit defaults, SMTP
field validation, private-file permissions, TLS mode exclusivity, approved account
bindings, identity-only egress, mailbox/profile selection, secret-change detection
and TLS-before-AUTH ordering. SMTP probe unit tests do not send messages and are
not evidence of an external provider accepting mail. No external SMTP credentials
or recipient were used during development; provider/inbox delivery remains a
reviewer-environment check.

## Remaining validation

A clean full deployment under reviewer-controlled DNS with a publicly trusted
certificate, real phone access, Android App Links and the complete credential
journey must still be exercised in that independent environment. The script's
successful compilation or environment check alone is not that evidence.

The original demo continues running on the validation host. No second complete
stack is started beside it merely to claim independent deployment acceptance.
Contact the maintainer with sanitized diagnostics if reproduction encounters a
problem; see the troubleshooting guide for information safe to share.
