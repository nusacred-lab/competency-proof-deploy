# Mailpit or external SMTP

Choose mail delivery before the first build and preparation. All three independent
identity realms use the selected transport. This choice affects verification and
password-recovery email; it does not change credential claims or issuer/holder keys.

## Mailpit: default local mailbox

Keep this configuration in `config/reviewer.json`:

```json
"mail": {
  "mode": "mailpit"
}
```

Configurations created before the mail selector was introduced can omit `mail`;
they retain the same Mailpit behavior and configuration fingerprint.

Mailpit starts inside Compose. Keycloak sends only synthetic `@example.test` mail
to it without external SMTP credentials. Open `http://127.0.0.1:29025` on the host,
or use your configured `mailbox_port`. Find a message for the account listed in the
private `installation.json` and use its action link. Do not publish the mailbox
through the public HTTPS tunnel or forward its port to other users.

## SMTP: send to approved reviewer inboxes

Replace the `mail` object with the contents of
[`config/smtp.example.json`](../config/smtp.example.json), then edit its values:

```json
"mail": {
  "mode": "smtp",
  "host": "smtp.your-provider.tld",
  "port": 587,
  "security": "starttls",
  "username": "your-smtp-username",
  "password_file": "/absolute/private/smtp/password",
  "from_address": "credentials@your-domain.tld",
  "from_display_name": "Competency Proof (demo)",
  "reply_to": "reviewer@your-domain.tld",
  "account_emails_file": "/absolute/private/smtp/account-emails.json"
}
```

Use `security: "starttls"` for an explicit TLS upgrade, commonly port 587, or
`security: "tls"` for implicit TLS, commonly port 465. Use the actual host/port
specified by your provider. Authentication with a username/password is required;
plaintext submission and OAuth-only providers are not supported by this adapter.
An application password may be required by the provider.

Store the password as one line in `password_file`, and copy
[`config/account-emails.example.json`](../config/account-emails.example.json) to
`account_emails_file`. Both files must be outside the checkout, regular files,
mode 0600 or stricter, inside a private directory. Edit the account file with four
reviewer-approved deliverable addresses:

- `applicant`: participant login and recovery inbox.
- `custodian-admin`: wallet administrator login/recovery inbox; must differ from
  the applicant because both belong to the same wallet realm.
- `issuer-admin`: issuer staff inbox.
- `company-admin`: employer staff inbox.

Mailbox aliases are acceptable when your mail provider supports them. Generated
`@example.test` addresses cannot receive external SMTP mail. These addresses identify
reviewer login accounts; they are not inserted into competency credential claims.
Use synthetic candidate labels in assessments regardless of the selected transport.

The sender address must be accepted by your provider. Configure sender verification,
SPF/DKIM or sandbox-recipient approval as required by that provider. Host firewalls,
cloud egress restrictions and the provider's submission port must permit the route.

Run preflight before building or preparing:

```sh
python3 scripts/preflight.py --android --network
```

For SMTP, preflight checks private inputs, a verified TLS connection and SMTP AUTH.
It does **not** send a message. Host-side success does not prove container egress
or final inbox delivery. Complete an intentional password-recovery journey from a
configured login page to verify the actual Keycloak-to-provider-to-inbox path.
Do not claim inbox delivery solely from successful authentication.

In SMTP mode, Compose leaves Mailpit disabled and publishes no mailbox listener.
Only the three identity services join a dedicated outbound SMTP network. That
network allows normal outbound access; it is not a destination-restricted firewall.
Other private application/protocol networks retain their existing isolation.

Keycloak receives the password in private realm-import files and persists its SMTP
settings in its own database. Those files remain inside the private runtime; no
password is placed in Compose or committed to Git. Treat runtime copies and
backups as secrets. Keycloak uses TLS certificate/hostname checks; no trust bypass
is configured. See the official [email settings](https://www.keycloak.org/docs/26.8.1/server_admin/#_email)
and [truststore guide](https://www.keycloak.org/server/keycloak-truststore).

## Existing installations and changes

For an older **unchanged Mailpit installation**, run `deploy.py prepare` once with
its original configuration before the next `up`; this generates the mail profile
and private overlay without changing the configuration fingerprint or accounts.
No new application/APK build is required when that configuration stays unchanged.

Choose SMTP before a new installation's builds. Changing mode, account email
bindings or the configuration requires a new runtime/project and the documented
build/preparation sequence. Existing Keycloak databases are not overwritten by
realm-import files. Do not assume editing JSON changes SMTP in a running realm.

The preparer also rejects a changed password-file value or account file after mail
settings have been prepared, preventing a silent mismatch with existing identity
state. Live SMTP credential rotation and account migration require deliberate
administrative changes outside this fresh-install adapter. A new disposable
reviewer installation is the supported path for trying another configuration.
