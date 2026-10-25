"""Compact network layout validation."""
from pathlib import Path
import ipaddress
import json
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from networking import overlay,validate_pool

class NetworkTests(unittest.TestCase):
    def test_private_pool_is_split_into_distinct_small_subnets(self):
        base=json.loads((ROOT/'compose.yaml').read_text())
        names=set(base['networks'])|{'smtp-egress'}
        result=overlay('10.240.0.0/24',names)['networks']
        nets=[ipaddress.ip_network(row['ipam']['config'][0]['subnet']) for row in result.values()]
        self.assertEqual(len(nets),len(names))
        self.assertTrue(all(n.prefixlen==28 for n in nets))
        self.assertTrue(all(not a.overlaps(b) for i,a in enumerate(nets) for b in nets[i+1:]))
    def test_pool_rejects_public_ipv6_host_bits_and_wrong_sizes(self):
        for value in ['8.8.8.0/24','::/24','10.240.0.1/24','10.240.0.0/16']:
            with self.assertRaises(ValueError):validate_pool(value)
if __name__=='__main__':unittest.main()
