"""Selectable synthetic mailbox or authenticated external SMTP configuration."""
import hashlib
import json
from pathlib import Path
import re
import smtplib
import ssl
import stat

ROLES = ('applicant', 'custodian-admin', 'issuer-admin', 'company-admin')


def settings(c):
    return c.get('mail', {'mode': 'mailpit'})


def hostname(value):
    return isinstance(value, str) and len(value) <= 253 and '.' in value and all(
        re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?', label)
        for label in value.split('.'))


def email(value):
    return isinstance(value, str) and len(value) <= 254 and value.count('@') == 1 and bool(
        re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}", value.split('@')[0])) and hostname(value.split('@')[1])


def private_path(value, root):
    if not isinstance(value, str):
        raise ValueError('SMTP input paths must be absolute private file paths')
    path = Path(value)
    if not path.is_absolute() or path.resolve() != path or root == path or root in path.parents:
        raise ValueError('SMTP input files must be canonical absolute paths outside this repository')
    return path


def validate(c, root):
    m = settings(c)
    if not isinstance(m, dict) or m.get('mode') not in ('mailpit', 'smtp'):
        raise ValueError('mail.mode must be mailpit or smtp')
    if m['mode'] == 'mailpit':
        if set(m) != {'mode'}:
            raise ValueError('Mailpit mode needs only mail.mode; remove external SMTP fields')
        return
    required = {'mode', 'host', 'port', 'security', 'username', 'password_file', 'from_address', 'account_emails_file'}
    if not required <= m.keys() or set(m) - required - {'reply_to', 'from_display_name'}:
        raise ValueError('SMTP fields must match config/smtp.example.json')
    if not hostname(m['host']):
        raise ValueError('SMTP host must be a DNS hostname without a scheme, port or path')
    if type(m['port']) is not int or not 1 <= m['port'] <= 65535:
        raise ValueError('SMTP port must be between 1 and 65535')
    if m['security'] not in ('starttls', 'tls'):
        raise ValueError('SMTP requires starttls or tls; plaintext submission is not supported')
    if not isinstance(m['username'], str) or not 1 <= len(m['username']) <= 320 or any(x in m['username'] for x in '\r\n\0'):
        raise ValueError('SMTP requires a valid authentication username')
    for key in ('from_address', 'reply_to'):
        if key in m and not email(m[key]):
            raise ValueError('SMTP ' + key + ' must be a plain email address')
    display = m.get('from_display_name', 'Competency Proof (demo)')
    if not isinstance(display, str) or not 1 <= len(display) <= 128 or any(x in display for x in '\r\n\0'):
        raise ValueError('Invalid SMTP sender display name')
    for key in ('password_file', 'account_emails_file'):
        private_path(m[key], root)


def read_private(path, limit):
    p = Path(path)
    if not p.is_file() or p.is_symlink() or stat.S_IMODE(p.stat().st_mode) & 0o077:
        raise ValueError('SMTP input files must be regular private files (mode 0600 or stricter)')
    if p.stat().st_size > limit:
        raise ValueError('SMTP input file is too large')
    return p.read_text()


def password(m):
    value = read_private(m['password_file'], 4096).removesuffix('\n').removesuffix('\r')
    if not value or any(x in value for x in '\r\n\0'):
        raise ValueError('SMTP password file must contain one nonempty line')
    return value


def account_emails(m):
    if m['mode'] == 'mailpit':
        return None
    try:
        values = json.loads(read_private(m['account_emails_file'], 16384))
    except json.JSONDecodeError:
        raise ValueError('Account email file must contain a valid JSON object') from None
    if not isinstance(values, dict) or set(values) != set(ROLES):
        raise ValueError('Account email file must map the four generated login roles')
    for address in values.values():
        if not email(address) or address.lower().endswith(('.test', '.invalid', '.example', '@example.org', '@example.com', '@example.net')):
            raise ValueError('SMTP account addresses must use reviewer-approved deliverable mailboxes')
    if values['applicant'].casefold() == values['custodian-admin'].casefold():
        raise ValueError('Applicant and custodian administrator need distinct wallet-realm email addresses')
    return values


def realm_settings(m):
    if m['mode'] == 'mailpit':
        return {'host': 'mail', 'port': '1025', 'from': 'noreply@example.test',
                'fromDisplayName': 'Competency Proof (demo)', 'auth': 'false', 'ssl': 'false', 'starttls': 'false'}
    result = {'host': m['host'], 'port': str(m['port']), 'from': m['from_address'],
              'fromDisplayName': m.get('from_display_name', 'Competency Proof (demo)'),
              'auth': 'true', 'user': m['username'], 'password': password(m),
              'ssl': str(m['security'] == 'tls').lower(), 'starttls': str(m['security'] == 'starttls').lower()}
    if 'reply_to' in m:
        result['replyTo'] = m['reply_to']
    return result


def compose_override(m):
    if m['mode'] == 'mailpit':
        return {'services': {'private-access': {'ports': ['127.0.0.1:${P6_MAIL_PORT:-29025}:8025']}}}
    return {'services': {name: {'networks': ['smtp-egress']} for name in ('keycloak', 'issuer-keycloak', 'company-keycloak')},
            'networks': {'smtp-egress': {'internal': False}}}


def state(m):
    value = {'smtp': realm_settings(m), 'accountEmails': account_emails(m)}
    return {'mode': m['mode'], 'settingsSha256': hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()}


def prepare_files(runtime, m):
    expected = state(m)
    stamp = runtime / 'mail-state.json'
    if stamp.exists() and json.loads(stamp.read_text()) != expected:
        raise ValueError('Mail credentials or account addresses changed; existing realms require deliberate migration or a fresh installation')
    stamp.write_text(json.dumps(expected) + '\n'); stamp.chmod(0o600)
    overlay = runtime / 'mail.compose.json'
    overlay.write_text(json.dumps(compose_override(m), indent=2) + '\n'); overlay.chmod(0o600)


def assert_prepared(runtime, m, verify_inputs=True):
    try:
        prepared = json.loads((runtime / 'mail-state.json').read_text())
        if prepared.get('mode') != m['mode'] or (verify_inputs and prepared != state(m)):
            raise ValueError('Mail inputs changed since preparation')
        if json.loads((runtime / 'mail.compose.json').read_text()) != compose_override(m):
            raise ValueError('Mail network configuration changed since preparation')
    except FileNotFoundError:
        raise ValueError('Mail configuration is not prepared; run deploy.py prepare first') from None


def check_inputs(m):
    if m['mode'] == 'smtp':
        password(m); account_emails(m)


def check_connection(m):
    """Check TLS and AUTH only. Never issue MAIL, RCPT or DATA commands."""
    if m['mode'] == 'mailpit':
        return
    secret = password(m)
    context = ssl.create_default_context()
    try:
        if m['security'] == 'tls':
            client = smtplib.SMTP_SSL(m['host'], m['port'], timeout=15, context=context)
        else:
            client = smtplib.SMTP(m['host'], m['port'], timeout=15)
        with client:
            client.ehlo()
            if m['security'] == 'starttls':
                client.starttls(context=context)
                client.ehlo()
            client.login(m['username'], secret)
    except (OSError, smtplib.SMTPException):
        # Server error text can contain account names or provider diagnostics.
        raise ValueError('SMTP TLS/authentication check failed; check connectivity, credentials and provider requirements') from None
