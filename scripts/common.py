"""Configuration and process helpers shared by deployment commands."""
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / 'sources.lock.json').read_text())
ROLES = ('wallet', 'issuer', 'employer', 'wallet_auth', 'issuer_auth', 'employer_auth')
PREFIXES = dict(zip(ROLES, ('dompet-identitas', 'lsp-nusantara', 'karya-instalasi',
                           'login-dompet-identitas', 'login-lsp-nusantara', 'login-karya-instalasi')))
PACKAGE = 'id.nusacred.wallet.reviewer'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fingerprint(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def load(path):
    c = json.loads(Path(path).read_text())
    required = {'project', 'runtime_directory', 'domains', 'https_bind_address', 'https_port',
                'admin_port', 'mailbox_port', 'tls_directory', 'minimum_memory_gib', 'minimum_disk_gib'}
    if not required <= c.keys() or set(c) - required - {'mail'}:
        raise ValueError('Configuration must contain the required deployment keys and optional mail settings')
    if not re.fullmatch(r'competency-proof-reviewer(?:-[a-z0-9-]{1,30})?', c['project']):
        raise ValueError('Use project competency-proof-reviewer or competency-proof-reviewer-<suffix>')
    if set(c['domains']) != set(ROLES):
        raise ValueError('Configure all six domain roles')
    if len(set(c['domains'].values())) != len(ROLES):
        raise ValueError('Each domain role must have its own hostname')
    for host in c['domains'].values():
        if not isinstance(host, str) or host != host.lower() or len(host) > 253:
            raise ValueError('Use lowercase DNS hostnames without a scheme, port or path')
        if '.' not in host or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in host.split('.')):
            raise ValueError('Invalid DNS hostname: ' + host)
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError('Use a DNS hostname rather than an IP address')
        if host.endswith(('.example.org', '.example.com', '.example.net', '.invalid', '.test', '.localhost')):
            raise ValueError('Replace example/reserved domains with reviewer-controlled DNS names')
        if host == 'demo.inoerawan.id' or host.endswith('.demo.inoerawan.id'):
            raise ValueError('Use reviewer-controlled domains, not the original demo domain')
    ipaddress.IPv4Address(c['https_bind_address'])
    ports = [c[k] for k in ('https_port', 'admin_port', 'mailbox_port')]
    if any(type(p) is not int or not 1 <= p <= 65535 for p in ports) or len(set(ports)) != 3:
        raise ValueError('Choose three distinct valid ports')
    for key in ('runtime_directory', 'tls_directory'):
        p = Path(c[key])
        if not p.is_absolute() or p.resolve() != p or any(ch.isspace() for ch in str(p)) or '$' in str(p):
            raise ValueError(key + ' must be a canonical absolute path without whitespace or dollar signs')
        if p == ROOT or ROOT in p.parents:
            raise ValueError(key + ' must be outside this repository')
    if 'runtime' not in Path(c['runtime_directory']).parts:
        raise ValueError('The private runtime path must include a directory named runtime')
    for key, minimum in (('minimum_memory_gib', 12), ('minimum_disk_gib', 20)):
        if type(c[key]) is not int or c[key] < minimum:
            raise ValueError(f'{key} must be at least {minimum}')
    from mailing import validate
    validate(c, ROOT)
    return c


def runtime(c):
    return Path(c['runtime_directory'])


def bind_runtime(c):
    r = runtime(c)
    r.mkdir(parents=True, exist_ok=True, mode=0o700)
    r.chmod(0o700)
    path = r / 'reviewer-config.json'
    if path.exists():
        if json.loads(path.read_text()) != c:
            raise ValueError('Configuration changed: use a fresh runtime/project for different domains or ports')
    else:
        if (r / 'installation.json').exists():
            raise ValueError('Refusing an existing installation without a reviewer configuration binding')
        path.write_text(json.dumps(c, indent=2) + '\n')
        path.chmod(0o600)
    return r


def clean_env():
    return {k: v for k, v in os.environ.items()
            if not k.startswith(('P6_', 'REVIEWER_', 'COMPOSE_')) and k != 'P2_SIGNING_DIRECTORY'}


def run(*args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, env=kwargs.pop('env', clean_env()), **kwargs)


def capture(*args, **kwargs):
    return run(*args, stdout=subprocess.PIPE, text=True, **kwargs).stdout.strip()


def json_write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')
    Path(path).chmod(0o600)


def replacement_map(c):
    return {PREFIXES[role] + '.demo.inoerawan.id': c['domains'][role] for role in ROLES}


def engine_for(c):
    import engine
    from mailing import settings
    engine.MAIL = settings(c)
    engine.HOSTS = {PREFIXES[role]: c['domains'][role] for role in ROLES}
    engine.REVIEWER_ENV = {'REVIEWER_' + role.upper() + '_HOST': c['domains'][role] for role in ROLES}
    engine.REVIEWER_ENV.update(REVIEWER_BIND_ADDRESS=c['https_bind_address'],
                              P6_HTTPS_PORT=str(c['https_port']), P6_ADMIN_PORT=str(c['admin_port']),
                              P6_MAIL_PORT=str(c['mailbox_port']))
    return engine
