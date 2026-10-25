"""Check reviewer deployment prerequisites without starting containers."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import ssl
import subprocess
import urllib.request
from common import ROOT, capture, load, run
from mailing import settings as mail_settings, check_inputs, check_connection


def certificate_checks(c):
    folder = Path(c['tls_directory'])
    cert, key = folder / 'fullchain.pem', folder / 'privkey.pem'
    if not cert.is_file() or not key.is_file():
        raise ValueError('TLS directory must contain fullchain.pem and privkey.pem')
    run('openssl', 'x509', '-in', cert, '-checkend', '86400', '-noout', stdout=subprocess.DEVNULL)
    for host in c['domains'].values():
        result = capture('openssl', 'x509', '-in', cert, '-checkhost', host, '-noout')
        if 'does match certificate' not in result:
            raise ValueError('TLS certificate does not cover ' + host)
    certificate_key = capture('openssl', 'x509', '-in', cert, '-pubkey', '-noout')
    private_key_public = capture('openssl', 'pkey', '-in', key, '-pubout', '-passin', 'pass:', stderr=subprocess.DEVNULL)
    if certificate_key != private_key_public:
        raise ValueError('TLS certificate and private key do not match')
    run('openssl', 'verify', '-purpose', 'sslserver', '-untrusted', cert, cert, stdout=subprocess.DEVNULL)
    print('PASS: certificate covers all six hosts, matches the key and is valid for at least 24 hours')


def check(c, network=False, android=False, ports=True):
    errors = []
    def step(label, fn):
        try:
            fn(); print('PASS: ' + label)
        except (ValueError, OSError, subprocess.SubprocessError, KeyError) as e:
            errors.append(label)
            print('FAIL: ' + label + ' (' + str(e) + ')')
    def tools():
        for tool in ('docker', 'openssl', 'git', 'python3', 'ip'):
            if shutil.which(tool) is None: raise ValueError('Missing ' + tool)
        if platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'AMD64'):
            raise ValueError('This package targets Linux x86_64')
        run('docker', 'compose', 'version', stdout=subprocess.DEVNULL)
        info = json.loads(capture('docker', 'info', '--format', '{{json .}}'))
        if info['Architecture'] not in ('x86_64', 'amd64') or info.get('OSType') != 'linux':
            raise ValueError('Docker must use Linux amd64 containers')
        if info['MemTotal'] < c['minimum_memory_gib'] * 1024**3:
            raise ValueError('Docker memory is below the configured minimum')
        # Runtime bind paths must refer to the local machine, not a remote daemon.
        context = json.loads(capture('docker', 'context', 'inspect'))[0]
        if not context['Endpoints']['docker']['Host'].startswith('unix://'):
            raise ValueError('Use a local Docker daemon for private bind mounts')
    step('Linux amd64, Docker access, Compose and supporting tools', tools)
    def disk():
        parent = Path(c['runtime_directory'])
        while not parent.exists(): parent = parent.parent
        if shutil.disk_usage(parent).free < c['minimum_disk_gib'] * 1024**3:
            raise ValueError('Insufficient free disk space at the private runtime')
        if not os.access(parent, os.W_OK): raise ValueError('Runtime parent is not writable')
    step('Private runtime disk capacity and write access', disk)
    step('TLS certificate and private key', lambda: certificate_checks(c))
    step('Mail configuration and private inputs', lambda: check_inputs(mail_settings(c)))
    if ports:
        def available():
            listeners_to_check = [(c['https_bind_address'], c['https_port']), ('127.0.0.1', c['admin_port'])]
            if mail_settings(c)['mode'] == 'mailpit':
                listeners_to_check.append(('127.0.0.1', c['mailbox_port']))
            for host, port in listeners_to_check:
                try:
                    with socket.socket() as probe: probe.bind((host, port))
                except PermissionError:
                    # A rootful Docker daemon can publish a privileged port even
                    # when this unprivileged CLI cannot bind it directly.
                    listeners = []
                    for table in ('/proc/net/tcp', '/proc/net/tcp6'):
                        for line in Path(table).read_text().splitlines()[1:]:
                            fields = line.split()
                            if fields[3] == '0A': listeners.append(int(fields[1].split(':')[1], 16))
                    if port in listeners: raise ValueError('Port already has a listener: ' + str(port))
                    print('NOTE: Docker must have permission to publish privileged port ' + str(port))
        step('Deployment ports are available', available)
    if android:
        from build import build_environment
        step('JDK 21 and Android SDK 37 build prerequisites', build_environment)
        step('Node.js for portal verification', lambda: run('node', '--version', stdout=subprocess.DEVNULL))
    if network:
        if mail_settings(c)['mode'] == 'smtp':
            step('SMTP TLS and authentication (no email sent)', lambda: check_connection(mail_settings(c)))
        def dns():
            for host in c['domains'].values():
                addresses = {r[4][0] for r in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
                if not addresses: raise ValueError('No DNS records: ' + host)
                print('DNS: ' + host + ' -> ' + ', '.join(sorted(addresses)))
        step('Reviewer domains resolve (routing must still be tested after startup)', dns)
        def registry():
            with urllib.request.urlopen('https://ghcr.io/token?service=ghcr.io&scope=repository:nusacred-lab/competency-proof-edge:pull', timeout=15) as response:
                if 'token' not in json.load(response): raise ValueError('Registry token unavailable')
        step('GHCR connectivity', registry)
    if errors:
        raise SystemExit('Preflight failed: ' + ', '.join(errors))
    print('Preflight passed. This does not prove phone connectivity or the credential flow.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, default=ROOT / 'config/reviewer.json')
    p.add_argument('--network', action='store_true', help='Check public DNS and registry connectivity')
    p.add_argument('--android', action='store_true', help='Also check the application build environment')
    p.add_argument('--running', action='store_true', help='Skip free-port checks for an already running stack')
    a = p.parse_args(); check(load(a.config), a.network, a.android, not a.running)


if __name__ == '__main__': main()
