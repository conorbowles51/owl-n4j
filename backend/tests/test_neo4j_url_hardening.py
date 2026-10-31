"""Neo4j refuses queries that fetch URLs or read server files (lx-neo4jconf).

The compose tests fail on the configuration before this change (no address block list, file URLs allowed, every APOC
procedure unrestricted). The live test runs deploy/checks/neo4j_url_refusals.py against a running Neo4j when
LOUPE_NEO4J_URL_CHECK_URI is set (with NEO4J_PASSWORD, .env or backend/.env); it is skipped otherwise.
"""
import importlib.util
import ipaddress
import os
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / 'deploy' / 'checks' / 'neo4j_url_refusals.py'


def _check_module():
    spec = importlib.util.spec_from_file_location('neo4j_url_refusals', CHECK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _neo4j_env():
    service = yaml.safe_load((ROOT / 'docker-compose.yml').read_text())['services']['neo4j']
    env = {}
    for item in service['environment']:
        key, _, value = item.partition('=')
        env[key] = value
    return env


def test_every_address_is_blocked_for_url_fetches():
    blocklist = _neo4j_env().get('NEO4J_internal_dbms_cypher__ip__blocklist', '')
    networks = [ipaddress.ip_network(cidr.strip()) for cidr in blocklist.split(',') if cidr.strip()]
    for address in ('127.0.0.1', '10.1.2.3', '172.17.0.1', '192.168.1.1', '169.254.169.254', '8.8.8.8',
                    '::1', 'fe80::1', 'fd00::1', '2001:4860:4860::8888'):
        ip = ipaddress.ip_address(address)
        assert any(ip in net for net in networks if net.version == ip.version), address
    # The private ranges stay listed on their own, so dropping the public lines never reopens the host.
    for cidr in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '169.254.0.0/16', '127.0.0.0/8',
                 '::1/128', 'fe80::/10', 'fc00::/7'):
        assert ipaddress.ip_network(cidr) in networks, cidr


def test_file_urls_are_refused():
    assert _neo4j_env().get('NEO4J_dbms_security_allow__csv__import__from__file__urls') == 'false'


def test_apoc_reaches_database_internals_only_where_the_app_needs_it():
    unrestricted = _neo4j_env()['NEO4J_dbms_security_procedures_unrestricted']
    # Empty would let the image's plugin installer write apoc.* back.
    assert unrestricted.strip()
    assert '*' not in unrestricted, unrestricted


def test_only_a_named_refusal_counts_as_refused():
    refused = _check_module().REFUSED
    # Messages measured from Neo4j 5.26.19 with the new settings.
    assert refused.search("Cannot load from URL 'http://127.0.0.1:7474/': access to /127.0.0.1 is blocked via the "
                          "configuration property internal.dbms.cypher_ip_blocklist ()")
    assert refused.search("Cannot load from URL 'file:///probe.csv': configuration property "
                          "'dbms.security.allow_csv_import_from_file_urls' is false ()")
    # Messages measured with the old settings: the server tried, so they are not refusals.
    assert not refused.search("Cannot load from URL 'http://169.254.169.254/computeMetadata/v1/': Couldn't load the "
                              "external resource at: http://169.254.169.254/computeMetadata/v1/ ()")
    assert not refused.search('Failed to invoke procedure `apoc.load.json`: Caused by: '
                              'com.fasterxml.jackson.core.JsonParseException: Unexpected character')


@pytest.mark.skipif(not os.environ.get('LOUPE_NEO4J_URL_CHECK_URI'),
                    reason='needs a running Neo4j: set LOUPE_NEO4J_URL_CHECK_URI (and NEO4J_PASSWORD)')
def test_running_neo4j_refuses_every_probe():
    module = _check_module()
    password = module._password()
    assert password, 'no Neo4j password'
    results = module.run(os.environ['LOUPE_NEO4J_URL_CHECK_URI'], os.environ.get('NEO4J_USER', 'neo4j'), password)
    not_refused = [(name, detail) for name, refused, detail in results if not refused]
    assert not not_refused, not_refused
    assert len(results) == len(module.PROBES)
