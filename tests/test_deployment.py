"""Regression checks for domain consistency and private deployment boundaries."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from common import bind_runtime, clean_env, engine_for, fingerprint, load, replacement_map


def configuration(root):
    c = json.loads((ROOT / 'config/reviewer.example.json').read_text())
    c['runtime_directory'] = str(root / 'runtime/reviewer')
    c['tls_directory'] = str(root / 'tls')
    c['domains'] = {role: role.replace('_', '-') + '.credentials.reviewer.dev' for role in c['domains']}
    return c


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.c = configuration(self.root)

    def read(self, c=None):
        path = self.root / 'config.json'
        path.write_text(json.dumps(self.c if c is None else c))
        return load(path)

    def test_accepts_six_reviewer_domains_and_separate_private_runtime(self):
        self.assertEqual(self.read(), self.c)

    def test_example_requires_real_configuration(self):
        with self.assertRaises(ValueError): load(ROOT / 'config/reviewer.example.json')

    def test_rejects_duplicate_original_reserved_and_malformed_domains(self):
        for host in ['https://wallet.reviewer.dev', 'wallet.reviewer.dev:443', 'wallet.reviewer.dev/path',
                     '127.0.0.1', 'wallet.example.org', 'wallet.demo.inoerawan.id', 'Wallet.reviewer.dev',
                     '-wallet.reviewer.dev', 'wallet..reviewer.dev', 'wallet.reviewer.dev\n']:
            with self.subTest(host=host):
                c = copy.deepcopy(self.c); c['domains']['wallet'] = host
                with self.assertRaises(ValueError): self.read(c)
        c = copy.deepcopy(self.c); c['domains']['wallet'] = c['domains']['issuer']
        with self.assertRaises(ValueError): self.read(c)

    def test_rejects_runtime_inside_repository_and_unsafe_paths(self):
        for value in [str(ROOT / 'runtime/demo'), '/tmp/a/../runtime/b', '/tmp/runtime/with space',
                      '/tmp/runtime/$VALUE', 'relative/runtime', '/tmp/no-runtime-component']:
            with self.subTest(value=value):
                c = dict(self.c, runtime_directory=value)
                with self.assertRaises(ValueError): self.read(c)

    def test_rejects_other_project_names_port_conflicts_and_small_capacity(self):
        for change in [dict(project='competency-proof-p7'), dict(admin_port=443), dict(https_port=0),
                       dict(https_port=True), dict(minimum_memory_gib=4), dict(minimum_disk_gib=1)]:
            with self.subTest(change=change):
                with self.assertRaises(ValueError): self.read(dict(self.c, **change))

    def test_runtime_binding_prevents_domain_and_port_changes(self):
        r = bind_runtime(self.c)
        self.assertEqual(r.stat().st_mode & 0o777, 0o700)
        self.assertEqual((r / 'reviewer-config.json').stat().st_mode & 0o777, 0o600)
        self.assertEqual(bind_runtime(self.c), r)
        with self.assertRaises(ValueError): bind_runtime(dict(self.c, https_port=29443))

    def test_refuses_unclassified_existing_installation(self):
        r = Path(self.c['runtime_directory']); r.mkdir(parents=True)
        (r / 'installation.json').write_text('{}')
        with self.assertRaises(ValueError): bind_runtime(self.c)

    def test_sanitizes_environment_before_compose(self):
        with patch.dict(os.environ, {'P6_RUNTIME':'other', 'COMPOSE_FILE':'evil', 'REVIEWER_WALLET_HOST':'evil',
                                    'P2_SIGNING_DIRECTORY':'operator-key', 'PATH':'/usr/bin'}):
            env = clean_env()
            self.assertNotIn('COMPOSE_FILE', env)
            self.assertNotIn('P6_RUNTIME', env)
            self.assertNotIn('REVIEWER_WALLET_HOST', env)
            self.assertNotIn('P2_SIGNING_DIRECTORY', env)
            self.assertEqual(env['PATH'], '/usr/bin')

    def test_all_generated_caddy_hosts_match_configuration(self):
        engine = engine_for(self.c)
        for name in ['ingress.caddy', 'private.caddy']:
            rendered = engine.render((ROOT / 'assets' / name).read_text())
            self.assertNotIn('@@', rendered)
            self.assertNotIn('demo.inoerawan.id', rendered)
            for role in ['wallet_auth', 'issuer_auth', 'employer_auth']:
                self.assertIn(self.c['domains'][role], rendered)
        self.assertEqual(engine.portal_host('dompet-identitas'), self.c['domains']['wallet'])
        self.assertEqual(engine.login_host('karya-instalasi'), self.c['domains']['employer_auth'])
        self.assertEqual(engine.REVIEWER_ENV['P6_HTTPS_PORT'], '443')

    def test_compose_only_exposes_the_edge_and_private_loopback_listeners(self):
        c = json.loads((ROOT / 'compose.yaml').read_text())
        self.assertNotIn('demo.inoerawan.id', json.dumps(c))
        for service, data in c['services'].items():
            for port in data.get('ports', []):
                if service != 'edge': self.assertTrue(port.startswith('127.0.0.1:'))
            self.assertNotIn('build', data)
        for service in ['custodian', 'issuer-backend', 'company-backend']:
            self.assertEqual(c['services'][service]['pull_policy'], 'never')
        self.assertNotIn('external', json.dumps(c['networks']))

    def test_baseline_and_source_lock_bind_the_same_application(self):
        manifest = json.loads((ROOT / 'baseline/release-manifest.json').read_text())
        lock = json.loads((ROOT / 'sources.lock.json').read_text())
        self.assertEqual(manifest['sources']['application']['commit'], lock['application']['commit'])
        self.assertEqual(len(manifest['images']), 11)
        for row in manifest['images'].values(): self.assertRegex(row['image'], r'@sha256:[0-9a-f]{64}$')

    def test_fingerprint_is_stable_and_domain_sensitive(self):
        self.assertEqual(fingerprint(self.c), fingerprint(dict(reversed(list(self.c.items())))))
        other = copy.deepcopy(self.c); other['domains']['wallet'] = 'changed.reviewer.dev'
        self.assertNotEqual(fingerprint(other), fingerprint(self.c))


class SigningOutputTests(unittest.TestCase):
    def test_accepts_legacy_and_scheme_specific_apksigner_output(self):
        from build import certificate_fingerprint
        digest = 'ab' * 32
        for label in ['Signer #1', 'V3.0 Signer']:
            self.assertEqual(certificate_fingerprint('Number of signers: 1\n' + label + ': certificate SHA-256 digest: ' + digest), ':'.join(['AB'] * 32))

    def test_rejects_missing_or_multiple_signers(self):
        from build import certificate_fingerprint
        for output in ['', 'Number of signers: 2\ncertificate SHA-256 digest: ' + 'ab' * 32,
                       'Number of signers: 1\ncertificate SHA-256 digest: ' + 'ab' * 32 + '\ncertificate SHA-256 digest: ' + 'cd' * 32]:
            with self.assertRaises(ValueError): certificate_fingerprint(output)


if __name__ == '__main__': unittest.main()
