import pytest

from backend.routers.discovery import endpoint_fingerprint, parse_nmap_xml, redact_rtsp_url, validate_private_cidr


def test_validate_private_cidr_limits_scope():
    assert str(validate_private_cidr("192.168.10.7/24")) == "192.168.10.0/24"
    with pytest.raises(ValueError):
        validate_private_cidr("8.8.8.0/24")
    with pytest.raises(ValueError):
        validate_private_cidr("10.0.0.0/16")


def test_redaction_and_duplicate_fingerprint_ignore_credentials():
    url = "rtsp://admin:very-secret@192.168.1.20:554/live"
    assert "very-secret" not in redact_rtsp_url(url)
    assert endpoint_fingerprint(url) == endpoint_fingerprint("rtsp://other:password@192.168.1.20:554/live")


def test_parse_nmap_xml_only_returns_up_hosts_with_open_ports():
    xml = b'''<nmaprun><host><status state="up"/><address addr="192.168.1.20" addrtype="ipv4"/><ports><port protocol="tcp" portid="554"><state state="open"/><service name="rtsp"/></port></ports></host><host><status state="down"/><address addr="192.168.1.21" addrtype="ipv4"/></host></nmaprun>'''
    assert parse_nmap_xml(xml) == [{"host": "192.168.1.20", "ports": [{"port": 554, "protocol": "tcp", "service": "rtsp", "product": None}]}]
