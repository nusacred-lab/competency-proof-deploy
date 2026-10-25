"""Allocate compact private Compose networks without changing Docker daemon settings."""
import ipaddress
import json
from pathlib import Path
import subprocess


def validate_pool(value):
    pool = ipaddress.ip_network(value, strict=True)
    if pool.version != 4 or pool.prefixlen != 24 or not any(pool.subnet_of(ipaddress.ip_network(block)) for block in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')):
        raise ValueError('network_cidr must be a private IPv4 /24 network')
    return pool


def occupied(project):
    ids = subprocess.check_output(['docker','network','ls','-q'],text=True).split()
    networks = json.loads(subprocess.check_output(['docker','network','inspect',*ids],text=True)) if ids else []
    values = []
    for network in networks:
        if (network.get('Labels') or {}).get('com.docker.compose.project') == project:
            continue
        for row in network.get('IPAM',{}).get('Config') or []:
            if row.get('Subnet'):
                net = ipaddress.ip_network(row['Subnet'])
                if net.version == 4: values.append(net)
    for row in json.loads(subprocess.check_output(['ip','-j','-4','route','show','table','main'],text=True)):
        if row.get('dst') not in (None,'default','0.0.0.0/0') and not row.get('dev','').startswith(('br-','docker')):
            values.append(ipaddress.ip_network(row['dst'],strict=False))
    return values


def overlay(pool, names):
    subnets = list(validate_pool(str(pool)).subnets(new_prefix=28))
    return {'networks': {name: {'ipam': {'config': [{'subnet': str(subnets[i])}]}} for i,name in enumerate(sorted(names))}}


def prepare(runtime, project, names, requested=None):
    path = runtime/'networks.compose.json'
    occupied_networks = occupied(project)
    record = runtime/'network-state.json'
    if record.exists():
        pool = validate_pool(json.loads(record.read_text())['cidr'])
        if requested and str(pool) != requested:
            raise ValueError('Existing runtime network selection cannot change')
    elif requested:
        pool = validate_pool(requested)
    else:
        pool = next((candidate for candidate in ipaddress.ip_network('10.240.0.0/12').subnets(new_prefix=24)
                     if not any(candidate.overlaps(other) for other in occupied_networks)), None)
        if pool is None: raise ValueError('No unused automatic subnet found; configure network_cidr explicitly')
    if any(pool.overlaps(other) for other in occupied_networks):
        raise ValueError('Selected network_cidr overlaps another Docker or host route')
    record.write_text(json.dumps({'cidr':str(pool)})+'\n');record.chmod(0o600)
    path.write_text(json.dumps(overlay(pool,names),indent=2)+'\n');path.chmod(0o600)


def check(runtime,names):
    if not (runtime/'network-state.json').exists():
        raise ValueError('Networks are not prepared; run deploy.py prepare first')
    pool = json.loads((runtime/'network-state.json').read_text())['cidr']
    if json.loads((runtime/'networks.compose.json').read_text()) != overlay(pool,names):
        raise ValueError('Prepared network configuration changed')
