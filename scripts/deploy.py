"""Prepare and operate an isolated reviewer deployment."""
import argparse
import copy
import json
from pathlib import Path
import shutil
from common import ROOT, PACKAGE, bind_runtime, capture, engine_for, fingerprint, json_write, load, run, runtime, sha


def baseline():
    return json.loads((ROOT / 'baseline/release-manifest.json').read_text())


def built(c):
    r = runtime(c)
    result = {}
    for kind in ('server', 'android'):
        record = json.loads((r / (kind + '-build.json')).read_text())
        if record['configurationSha256'] != fingerprint(c) or record['sourceRecordSha256'] != sha(r / 'source-record.json'):
            raise ValueError('Build does not match this configuration/source record: ' + kind)
        result[kind] = record
    if sha(r / 'artifacts/competency-proof-reviewer.apk') != result['android']['apkSha256']:
        raise ValueError('Signed APK changed after build')
    for image in result['server']['images'].values():
        if capture('docker', 'image', 'inspect', '--format', '{{.Id}}', image) != image:
            raise ValueError('A reviewer application image is missing')
    return result


def prepare(c):
    from preflight import certificate_checks
    certificate_checks(c)
    from mailing import check_inputs, settings
    check_inputs(settings(c))
    r = bind_runtime(c)
    records = built(c)
    manifest = copy.deepcopy(baseline())
    for service, image in records['server']['images'].items():
        manifest['images'][service]['image'] = image
    # This is a derived local manifest, not the upstream CI attestation.
    manifest['reviewerBuild'] = dict(configurationSha256=fingerprint(c),
        server=records['server'], android=records['android'])
    manifest_path = r / 'reviewer-manifest.json'
    json_write(manifest_path, manifest)
    engine = engine_for(c)
    engine.prepare(r, manifest, manifest_path, certificate=Path(c['tls_directory']), project=c['project'])
    shutil.copyfile(r / 'artifacts/assetlinks.json', r / 'assetlinks/.well-known/assetlinks.json')
    (r / 'assetlinks/.well-known/assetlinks.json').chmod(0o644)
    engine.compose(r / 'compose.env', 'config', '--quiet')
    print('Private runtime prepared. Credentials are in installation.json; do not publish that file.')


def assert_prepared(c):
    r = bind_runtime(c)
    engine = engine_for(c)
    manifest = engine.check_runtime(r)
    if manifest.get('reviewerBuild', {}).get('configurationSha256') != fingerprint(c):
        raise ValueError('Prepared deployment does not match configuration')
    expected = {k: row['image'] for k, row in baseline()['images'].items()}
    records = built(c)
    expected.update(records['server']['images'])
    if {k: row['image'] for k, row in manifest['images'].items()} != expected:
        raise ValueError('Prepared image selection changed; run prepare after a deliberate rebuild')
    links = json.loads((r / 'assetlinks/.well-known/assetlinks.json').read_text())
    target = links[0]['target']
    if target['package_name'] != PACKAGE or target['sha256_cert_fingerprints'] != [records['android']['certificateSha256']]:
        raise ValueError('Published App Links association does not match the signed APK')
    return engine


def readiness(c):
    import urllib.request
    import ssl
    engine = assert_prepared(c)
    r = runtime(c)
    # Public checks intentionally use system CA trust and normal DNS, as a reviewer phone does.
    for role, service in [('wallet', 'custodian'), ('issuer', 'issuer'), ('employer', 'company')]:
        url = 'https://' + c['domains'][role] + '/api/v1/portal-config'
        with urllib.request.urlopen(url, timeout=15) as response:
            data = json.load(response)
        if data['service'] != service or data['walletOrigin'] != 'https://' + c['domains']['wallet']:
            raise ValueError('Wrong portal configuration: ' + role)
        print('PASS: public HTTPS portal ' + role)
    for entity, domain, realm, _ in engine.ENTITIES:
        role = {'wallet':'wallet_auth', 'issuer':'issuer_auth', 'company':'employer_auth'}[entity]
        origin = 'https://' + c['domains'][role] + '/realms/' + realm
        with urllib.request.urlopen(origin + '/.well-known/openid-configuration', timeout=15) as response:
            discovery = json.load(response)
        if discovery['issuer'] != origin:
            raise ValueError('OIDC issuer mismatch: ' + entity)
        print('PASS: public OIDC discovery ' + entity)
    url = 'https://' + c['domains']['wallet'] + '/.well-known/assetlinks.json'
    with urllib.request.urlopen(url, timeout=15) as response:
        if json.load(response) != json.loads((r / 'artifacts/assetlinks.json').read_text()):
            raise ValueError('Public App Links association differs from the APK build')
    print('PASS: public App Links association. Run the real credential walkthrough next.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['pull', 'verify-images', 'prepare', 'up', 'stop', 'status', 'ready'])
    p.add_argument('--config', type=Path, default=ROOT / 'config/reviewer.json')
    a = p.parse_args(); c = load(a.config)
    if a.command == 'pull':
        for row in baseline()['images'].values():
            run('docker', 'pull', '--platform', 'linux/amd64', row['image'])
    elif a.command == 'verify-images':
        m = baseline()
        engine_for(c).verify(ROOT / 'baseline/release-manifest.json', m['workflow']['commit'], m['workflow']['ref'])
    elif a.command == 'prepare': prepare(c)
    elif a.command == 'ready': readiness(c)
    else:
        engine = assert_prepared(c)
        if a.command == 'up':
            for row in engine.check_runtime(runtime(c))['images'].values():
                capture('docker', 'image', 'inspect', '--format', '{{.Id}}', row['image'])
            engine.start(runtime(c))
        else:
            engine.compose(runtime(c) / 'compose.env', 'stop' if a.command == 'stop' else 'ps')


if __name__ == '__main__':
    main()
