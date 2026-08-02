"""Tests for CIDR to OpenSearch query conversion."""

from app.utils.cidr import (
    cidr_to_opensearch_filter,
    cidr_to_range,
    cidr_to_wildcard,
    is_cidr,
    validate_cidr,
)


def test_is_cidr():
    assert is_cidr("10.0.0.0/8") is True
    assert is_cidr("192.168.1.0/24") is True
    assert is_cidr("8.8.8.8") is False
    assert is_cidr("::1") is False


def test_validate_cidr():
    assert validate_cidr("10.0.0.0/8") is True
    assert validate_cidr("192.168.1.0/24") is True
    assert validate_cidr("172.16.0.0/12") is True
    assert validate_cidr("10.0.0.0/33") is False
    assert validate_cidr("not-a-cidr") is False


def test_cidr_to_wildcard_slash8():
    assert cidr_to_wildcard("10.0.0.0/8") == "10.*.*.*"
    assert cidr_to_wildcard("192.0.0.0/8") == "192.*.*.*"


def test_cidr_to_wildcard_slash16():
    assert cidr_to_wildcard("10.0.0.0/16") == "10.0.*.*"
    assert cidr_to_wildcard("192.168.0.0/16") == "192.168.*.*"


def test_cidr_to_wildcard_slash24():
    assert cidr_to_wildcard("10.0.1.0/24") == "10.0.1.*"
    assert cidr_to_wildcard("192.168.1.0/24") == "192.168.1.*"


def test_cidr_to_range():
    gte, lte = cidr_to_range("192.168.1.0/24")
    assert gte == "192.168.1.0"
    assert lte == "192.168.1.255"

    gte, lte = cidr_to_range("10.0.0.0/8")
    assert gte == "10.0.0.0"
    assert lte == "10.255.255.255"


def test_cidr_to_opensearch_filter_slash8():
    result = cidr_to_opensearch_filter("10.0.0.0/8", ["src", "source.ip"])
    assert "bool" in result
    assert "should" in result["bool"]
    assert len(result["bool"]["should"]) == 2
    wildcards = [clause["wildcard"] for clause in result["bool"]["should"]]
    assert any("src" in w and w["src"] == "10.*.*.*" for w in wildcards)
    assert any("source.ip" in w and w["source.ip"] == "10.*.*.*" for w in wildcards)


def test_cidr_to_opensearch_filter_slash24():
    result = cidr_to_opensearch_filter("192.168.1.0/24", ["dst"])
    assert len(result["bool"]["should"]) == 1
    clause = result["bool"]["should"][0]
    assert "wildcard" in clause
    assert clause["wildcard"]["dst"] == "192.168.1.*"


def test_cidr_to_opensearch_filter_non_standard():
    result = cidr_to_opensearch_filter("10.0.0.0/21", ["src"])
    assert "bool" in result
    for clause in result["bool"]["should"]:
        assert "range" in clause
        assert clause["range"]["src"]["gte"] == "10.0.0.0"
        assert clause["range"]["src"]["lte"] == "10.0.7.255"
