# Credential walkthrough

Run the public readiness check first. Keep the prepared stack and your HTTPS route
running throughout. Install the reviewer-signed APK and verify its App Links.
Use only synthetic candidate labels and assessment data.

## 1. Sign in to the wallet

Read the generated `users.applicant.email` and `users.applicant.password` from the
private runtime's `installation.json`. Sign in on the Android wallet. The wallet
provisions its server-side account and displays a recipient code. Copy that code
for the issuer. Do not invent a recipient code or use an email in its place.

## 2. Issue and receive

Open your configured issuer domain. Sign in using `users.issuer-admin` from the
same private file. Choose **New assessment**, enter a synthetic candidate label,
the participant recipient code, competency `DEMO-ELEC-001`, and **Competent**.
Save the assessment, then choose **Create credential offer**. If you previously ran
the automated flow check, reuse its printed synthetic candidate label for this
recipient; the application intentionally rejects reassignment to another label.

Scan the offer QR with the wallet, or open its link on the Android phone. Review
the recipient and credential, then explicitly approve receipt. Confirm the
credential appears in the wallet and open its details. The issuer and walt.id
wallet perform real issuance and storage; viewing an offer is not acceptance.

## 3. Configure employer trust and the job

Open your employer domain and sign in with `users.company-admin`. Set the job's
competency to `DEMO-ELEC-001` and the required result to **Competent**.

In **Trusted issuers**, review LSP Nusantara's published identity. Use **Demo
walkthrough only**, enter a meaningful note identifying this as a synthetic review,
confirm the organization and identity, and approve trust. HTTPS and the issuer's
self-published profile do not establish real accreditation.

## 4. Present and verify

Open the employer's public job page in a separate browser session or choose its
public view. Select **Check my competency**. Scan the resulting QR in the wallet,
select the received credential, review the requested information and approve
presentation.

Wait for the employer page to show that the credential meets the role's
requirements. Confirm the same finalized record appears in the employer portal.
The result combines walt.id proof verification with issuer trust, credential
validity, the competency code and the competent assessment result.

For an optional negative demonstration, change the job competency and create a
new request. The original credential should fail the new requirement. Existing
final results remain unchanged.

## Automated real-service check

```sh
python3 scripts/check-flow.py
```

This optional command signs in through real identity services, issues and receives
a synthetic credential, reads it back from the wallet, presents it and checks
positive/negative results. It uses the configured public HTTPS routes, creates
records and changes the reviewer employer's job/trust settings. Run it on a
reviewer instance, before preparing your final screen recording. Repeated runs retain the synthetic candidate/account binding and create new
assessment and verification records. Private results stay under the configured runtime.

The command exercises native OIDC/PKCE and credential APIs; it does not operate an
Android phone, scan an optical QR or prove biometric/device behavior. Demonstrate
those steps separately when recording the 3–5 minute walkthrough.
