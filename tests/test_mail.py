"""Mail selection, credential privacy and SMTP transport boundary checks."""
import copy
import json
from pathlib import Path
import smtplib
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import mailing
from common import engine_for, load
from test_deployment import configuration


class MailTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.c = configuration(self.root)
        self.secret = self.root / 'password'
        self.secret.write_text('unit-test-password\n'); self.secret.chmod(0o600)
        self.emails = self.root / 'account-emails.json'
        self.addresses = {role: role + '@reviewer.dev' for role in mailing.ROLES}
        self.emails.write_text(json.dumps(self.addresses)); self.emails.chmod(0o600)
        self.m = dict(mode='smtp', host='smtp.reviewer.dev', port=587, security='starttls',
                      username='reviewer', password_file=str(self.secret), from_address='demo@reviewer.dev',
                      account_emails_file=str(self.emails))

    def test_legacy_config_still_defaults_to_mailpit_without_changing_its_hash_input(self):
        c = copy.deepcopy(self.c); c.pop('mail', None)
        path = self.root / 'config.json'; path.write_text(json.dumps(c))
        self.assertEqual(load(path), c)
        self.assertEqual(mailing.settings(c), {'mode':'mailpit'})

    def test_smtp_accepts_only_supported_fields_tls_and_authentication(self):
        mailing.validate(dict(self.c, mail=self.m), ROOT)
        for changes in [dict(security='none'), dict(security='ssl'), dict(username=''), dict(port=True),
                        dict(port=0), dict(host='smtp://smtp.reviewer.dev'), dict(password='inline'),
                        dict(from_address='Sender <demo@reviewer.dev>'), dict(reply_to='a@b.dev\r\nBcc: x@y.dev')]:
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError): mailing.validate(dict(self.c, mail=dict(self.m, **changes)), ROOT)
        with self.assertRaises(ValueError): mailing.validate(dict(self.c, mail={'mode':'mailpit','password':'inline'}), ROOT)

    def test_private_inputs_are_required_and_permissions_are_checked(self):
        mailing.check_inputs(self.m)
        self.secret.chmod(0o644)
        with self.assertRaises(ValueError): mailing.check_inputs(self.m)
        self.secret.chmod(0o600); self.secret.write_text('line1\nline2')
        with self.assertRaises(ValueError): mailing.check_inputs(self.m)

    def test_rejects_missing_reserved_and_duplicate_wallet_recipients(self):
        for values in [{}, dict(self.addresses, applicant='synthetic@example.test'),
                       dict(self.addresses, applicant=self.addresses['custodian-admin'].upper())]:
            self.emails.write_text(json.dumps(values))
            with self.assertRaises(ValueError): mailing.account_emails(self.m)

    def test_realm_settings_keep_tls_modes_exclusive_and_authenticated(self):
        for security, ssl, starttls in [('starttls','false','true'), ('tls','true','false')]:
            data = mailing.realm_settings(dict(self.m, security=security))
            self.assertEqual((data['ssl'], data['starttls'], data['auth']), (ssl,starttls,'true'))
            self.assertEqual(data['password'], 'unit-test-password')
        pit = mailing.realm_settings({'mode':'mailpit'})
        self.assertEqual((pit['host'], pit['auth']), ('mail','false'))
        self.assertNotIn('password', pit)

    def test_smtp_overlay_only_grants_identity_services_egress_and_contains_no_credentials(self):
        overlay = mailing.compose_override(self.m)
        self.assertEqual(set(overlay['services']), {'keycloak','issuer-keycloak','company-keycloak'})
        self.assertEqual(overlay['networks'], {'smtp-egress': {'internal': False}})
        self.assertNotIn('unit-test-password', json.dumps(overlay))
        self.assertNotIn('ports', json.dumps(overlay))
        base = json.loads((ROOT / 'compose.yaml').read_text())
        self.assertEqual(base['services']['mail']['profiles'], ['mailpit'])
        self.assertFalse(any(':8025' in p for p in base['services']['private-access']['ports']))

    def test_mailbox_route_is_removed_in_smtp_mode_and_present_in_mailpit(self):
        engine = engine_for(dict(self.c, mail=self.m))
        rendered = engine.render((ROOT / 'assets/private.caddy').read_text())
        self.assertNotIn(':8025', rendered)
        self.assertNotIn('@@', rendered)
        engine = engine_for(dict(self.c, mail={'mode':'mailpit'}))
        self.assertIn('reverse_proxy mail:8025', engine.render((ROOT / 'assets/private.caddy').read_text()))

    def test_prepared_binding_rejects_password_changes_or_tampered_egress(self):
        r = self.root / 'prepared'; r.mkdir()
        mailing.prepare_files(r, self.m); mailing.assert_prepared(r, self.m)
        self.assertEqual((r / 'mail-state.json').stat().st_mode & 0o777, 0o600)
        self.assertNotIn('unit-test-password', (r / 'mail-state.json').read_text())
        (r / 'mail.compose.json').write_text('{}')
        with self.assertRaises(ValueError): mailing.assert_prepared(r, self.m)
        mailing.prepare_files(r, self.m)
        self.secret.write_text('rotated-secret')
        with self.assertRaises(ValueError): mailing.assert_prepared(r, self.m)
        with self.assertRaises(ValueError): mailing.prepare_files(r, self.m)

    def test_status_and_stop_can_validate_topology_without_available_smtp_password(self):
        r = self.root / 'prepared'; r.mkdir()
        mailing.prepare_files(r, self.m)
        self.secret.unlink()
        mailing.assert_prepared(r, self.m, verify_inputs=False)
        with self.assertRaises(ValueError): mailing.assert_prepared(r, self.m)

    def test_smtp_startup_does_not_require_an_inactive_mailpit_image(self):
        from deploy import selected_images
        manifest = {'images': {'mail': {'image':'mail-fixture'}, 'issuer': {'image':'issuer-fixture'}}}
        self.assertEqual(set(selected_images(dict(self.c, mail=self.m), manifest)), {'issuer'})
        self.assertEqual(set(selected_images(dict(self.c, mail={'mode':'mailpit'}), manifest)), {'mail','issuer'})

    def test_compose_resolves_both_modes_without_mailbox_or_egress_leaks(self):
        import shutil
        import subprocess
        if not shutil.which('docker'):
            self.skipTest('Docker Compose CLI not installed')
        manifest = json.loads((ROOT / 'baseline/release-manifest.json').read_text())
        for mode in ('mailpit', 'smtp'):
            m = {'mode':'mailpit'} if mode == 'mailpit' else self.m
            engine = engine_for(dict(self.c, mail=m))
            env = dict(engine.REVIEWER_ENV, P6_RUNTIME=str(self.root), P6_PROJECT_NAME=self.c['project'])
            for name, row in manifest['images'].items():
                env['P6_' + name.upper().replace('-', '_') + '_IMAGE'] = row['image']
            for entity in ('wallet','issuer','company'):
                env['P6_' + entity.upper() + '_DB_PASSWORD'] = 'configuration-fixture'
                env['P6_' + entity.upper() + '_BOOTSTRAP_PASSWORD'] = 'configuration-fixture'
            envfile = self.root / 'compose.env'
            envfile.write_text(''.join(key + '=' + value + '\n' for key, value in env.items()))
            overlay = self.root / 'mail.compose.json'; overlay.write_text(json.dumps(mailing.compose_override(m)))
            args = ['docker','compose','--env-file',str(envfile),'-f',str(ROOT/'compose.yaml'),'-f',str(overlay)]
            if mode == 'mailpit': args += ['--profile','mailpit']
            parsed = json.loads(subprocess.check_output(args + ['config','--format','json'], text=True))
            private_ports = parsed['services']['private-access'].get('ports', [])
            self.assertEqual(any(port['target'] == 8025 for port in private_ports), mode == 'mailpit')
            self.assertEqual('mail' in parsed['services'], mode == 'mailpit')
            for name in ('keycloak','issuer-keycloak','company-keycloak'):
                self.assertEqual('smtp-egress' in parsed['services'][name]['networks'], mode == 'smtp')

    def test_network_probe_uses_starttls_before_auth_and_never_sends_mail(self):
        client = MagicMock(); client.__enter__.return_value = client
        with patch('mailing.smtplib.SMTP', return_value=client): mailing.check_connection(self.m)
        events = [call[0] for call in client.method_calls]
        self.assertLess(events.index('starttls'), events.index('login'))
        client.login.assert_called_once_with('reviewer', 'unit-test-password')
        client.sendmail.assert_not_called(); client.send_message.assert_not_called()

    def test_tls_probe_uses_verified_ssl_context(self):
        client = MagicMock(); client.__enter__.return_value = client
        with patch('mailing.smtplib.SMTP_SSL', return_value=client) as factory:
            mailing.check_connection(dict(self.m, security='tls', port=465))
        context = factory.call_args.kwargs['context']
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, 2)
        client.starttls.assert_not_called()

    def test_tls_failure_prevents_authentication_and_does_not_expose_server_error(self):
        client = MagicMock(); client.__enter__.return_value = client
        client.starttls.side_effect = smtplib.SMTPException('sensitive provider diagnostic')
        with patch('mailing.smtplib.SMTP', return_value=client):
            with self.assertRaises(ValueError) as error: mailing.check_connection(self.m)
        self.assertNotIn('sensitive', str(error.exception))
        client.login.assert_not_called()


if __name__ == '__main__': unittest.main()
