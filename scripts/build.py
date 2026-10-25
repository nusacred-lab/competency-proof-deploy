"""Build reviewer-domain application images and a reviewer-signed Android APK."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
from common import ROOT, LOCK, PACKAGE, bind_runtime, capture, fingerprint, json_write, load, replacement_map, run, sha


def source(c, local=None):
    r = bind_runtime(c)
    target = r / 'source'
    if target.exists():
        record = json.loads((r / 'source-record.json').read_text())
        if record['configurationSha256'] != fingerprint(c) or record['applicationCommit'] != LOCK['application']['commit']:
            raise ValueError('Source binding changed; use a new private runtime')
        if capture('git', 'rev-parse', 'HEAD', cwd=target) != LOCK['application']['commit']:
            raise ValueError('Application source commit changed')
        verify_source(target, record)
        return target
    run('git', 'clone', '--no-hardlinks', '--no-checkout', str(local or LOCK['application']['repository']), target)
    run('git', 'checkout', '--detach', LOCK['application']['commit'], cwd=target)
    if sha(target / 'gradle/wrapper/gradle-wrapper.jar') != LOCK['wrapperSha256']:
        raise ValueError('Gradle wrapper checksum mismatch')
    modified = {}
    tracked = capture('git', 'ls-files', cwd=target).splitlines()
    for name in tracked:
        p = target / name
        if p.suffix not in ('.kt', '.kts', '.xml', '.js', '.mjs'):
            continue
        text = p.read_text()
        updated = text
        for old, new in sorted(replacement_map(c).items(), key=lambda item: -len(item[0])):
            updated = updated.replace(old, new)
        # Keep legacy diagnostic aliases bound to the reviewer wallet too.
        updated = updated.replace('wallet.demo.inoerawan.id', c['domains']['wallet'])
        if name == 'ci/test_portal_boot.mjs':
            old = "harness(host + '.demo.inoerawan.id')"
            if updated.count(old) != 1:
                raise ValueError('Unexpected portal test hostname construction')
            host_map = {prefix: c['domains'][role] for role, prefix in
                        [('issuer', 'lsp-nusantara'), ('employer', 'karya-instalasi'), ('wallet', 'dompet-identitas')]}
            updated = updated.replace(old, 'harness((' + json.dumps(host_map) + ')[host])')
        if name == 'android-wallet/build.gradle.kts':
            old = 'applicationId = "id.nusacred.wallet"'
            if updated.count(old) != 1:
                raise ValueError('Unexpected application ID declaration')
            updated = updated.replace(old, 'applicationId = "' + PACKAGE + '"')
        if updated != text:
            p.write_text(updated)
            modified[name] = sha(p)
    if not {'backend-common/src/main/kotlin/id/nusacred/common/PortalRoutes.kt',
            'backend-common/src/main/kotlin/id/nusacred/common/IssuerProfile.kt',
            'android-wallet/build.gradle.kts', 'android-wallet/src/release/AndroidManifest.xml'} <= modified.keys():
        raise ValueError('The pinned source no longer matches the domain adaptation contract')
    record = dict(applicationCommit=LOCK['application']['commit'], configurationSha256=fingerprint(c), files=modified)
    json_write(r / 'source-record.json', record)
    return target


def verify_source(target, record):
    expected = record['files']
    changed = set(capture('git', 'diff', '--name-only', cwd=target).splitlines())
    if changed != set(expected) or any(sha(target / name) != digest for name, digest in expected.items()):
        raise ValueError('Adapted source was modified; refusing an unrecorded build')
    if capture('git', 'ls-files', '--others', '--exclude-standard', cwd=target):
        raise ValueError('Untracked files in source checkout')


def build_environment():
    java = capture('java', '-version', stderr=subprocess.STDOUT)
    if not re.search(r'version "21[.\"]', java):
        raise ValueError('Set JAVA_HOME and PATH to JDK 21')
    sdk = Path(os.environ.get('ANDROID_HOME', os.environ.get('ANDROID_SDK_ROOT', '/missing-android-sdk')))
    if not (sdk / 'platforms/android-37.0/android.jar').exists() or not (sdk / 'build-tools/37.0.0/apksigner').exists():
        raise ValueError('Set ANDROID_HOME to an SDK with platforms;android-37.0 and build-tools;37.0.0')
    return sdk


def init_signing(c):
    folder = bind_runtime(c) / 'signing'
    folder.mkdir(exist_ok=True, mode=0o700)
    key, password = folder / 'reviewer.p12', folder / 'password'
    if key.exists() and password.exists():
        print('Existing reviewer signing identity retained.')
        return
    if key.exists() or password.exists():
        raise ValueError('Incomplete signing identity; recover its matching key/password rather than overwriting it')
    value = secrets.token_urlsafe(36)
    password.write_text(value + '\n'); password.chmod(0o600)
    env = dict(os.environ, REVIEWER_KEY_PASSWORD=value)
    run('keytool', '-genkeypair', '-keystore', key, '-storetype', 'PKCS12', '-alias', 'reviewer',
        '-keyalg', 'RSA', '-keysize', '3072', '-validity', '3650',
        '-dname', 'CN=Competency Proof Reviewer Demo', '-storepass:env', 'REVIEWER_KEY_PASSWORD',
        '-keypass:env', 'REVIEWER_KEY_PASSWORD', env=env)
    key.chmod(0o600)
    print('Reviewer signing identity created in the private runtime. Retain it for APK updates.')


def certificate_fingerprint(output):
    matches = set(re.findall(r'certificate SHA-256 digest:\s*([a-fA-F0-9]{64})', output))
    if len(matches) != 1 or not re.search(r'Number of signers:\s*1(?:\s|$)', output):
        raise ValueError('Expected exactly one verified APK signing certificate')
    digest = matches.pop().upper()
    return ':'.join(digest[i:i+2] for i in range(0, 64, 2))


def android(c, target):
    sdk = build_environment()
    r = bind_runtime(c)
    if not (r / 'signing/reviewer.p12').exists():
        raise ValueError('Run init-signing first')
    run('./gradlew', ':android-wallet:assembleRelease', ':android-wallet:lintRelease',
        '--dependency-verification', 'strict', '--no-daemon', cwd=target)
    output = r / 'artifacts'; output.mkdir(exist_ok=True)
    unsigned = target / 'android-wallet/build/outputs/apk/release/android-wallet-release-unsigned.apk'
    aligned = output / 'wallet-aligned.apk'
    apk = output / 'competency-proof-reviewer.apk'
    tools = sdk / 'build-tools/37.0.0'
    run(tools / 'zipalign', '-f', '-p', '4', unsigned, aligned)
    run(tools / 'apksigner', 'sign', '--ks', r / 'signing/reviewer.p12', '--ks-key-alias', 'reviewer',
        '--ks-pass', 'file:' + str(r / 'signing/password'), '--out', apk, aligned)
    verified = capture(tools / 'apksigner', 'verify', '--verbose', '--print-certs', apk)
    cert = certificate_fingerprint(verified)
    json_write(r / 'android-build.json', dict(configurationSha256=fingerprint(c), packageName=PACKAGE,
        applicationCommit=LOCK['application']['commit'], sourceRecordSha256=sha(r / 'source-record.json'),
        apkSha256=sha(apk), certificateSha256=cert))
    json_write(output / 'assetlinks.json', [{'relation': ['delegate_permission/common.handle_all_urls'],
        'target': {'namespace': 'android_app', 'package_name': PACKAGE, 'sha256_cert_fingerprints': [cert]}}])
    (output / 'SHA256SUMS').write_text(sha(apk) + '  ' + apk.name + '\n')
    aligned.unlink()
    print('Signed APK and generated App Links association: ' + str(output))


def server(c, target):
    build_environment()
    r = bind_runtime(c)
    for script in ['check_policy.py', 'verify_dependency_review.py', 'check_api_contract.py']:
        run('python3', 'ci/' + script, cwd=target)
    run('node', 'ci/test_portal_boot.mjs', cwd=target)
    run('./gradlew', ':shared-contracts:jvmTest', ':backend-common:test', ':custodian-backend:test',
        ':integration-tests:test', ':issuer-backend:installDist', ':company-backend:installDist',
        ':custodian-backend:installDist', ':web-portals:wasmJsBrowserDistribution',
        '--dependency-verification', 'strict', '--no-daemon', cwd=target)
    images = {}
    for service in ('issuer', 'custodian', 'company'):
        tag = c['project'] + '-' + service + ':' + fingerprint(c)[:12]
        run('docker', 'build', '--platform', 'linux/amd64', '-f', 'deploy/Containerfile.' + service,
            '--build-arg', 'SOURCE_REVISION=' + LOCK['application']['commit'],
            '--label', 'org.nusacred.reviewer.configuration=' + fingerprint(c), '-t', tag, '.', cwd=target)
        images[service] = capture('docker', 'image', 'inspect', '--format', '{{.Id}}', tag)
    json_write(r / 'server-build.json', dict(configurationSha256=fingerprint(c), images=images,
        applicationCommit=LOCK['application']['commit'], sourceRecordSha256=sha(r / 'source-record.json')))
    print('Three application images built and recorded by immutable local image ID.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['source', 'init-signing', 'android', 'server'])
    p.add_argument('--config', type=Path, default=ROOT / 'config/reviewer.json')
    p.add_argument('--source', type=Path, help='Optional local Git clone used as a source mirror')
    a = p.parse_args(); c = load(a.config)
    if a.command == 'init-signing':
        init_signing(c)
    else:
        target = source(c, a.source)
        if a.command == 'android': android(c, target)
        if a.command == 'server': server(c, target)


if __name__ == '__main__':
    main()
