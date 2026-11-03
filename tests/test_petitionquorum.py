import json

import pytest

from conftest import (
    CREATOR,
    DOWN,
    MISSING,
    REACHABLE,
    SHORT,
    SIGNER1,
    SIGNER2,
    SIGNER3,
)

LONG_BODY = b"x" * 200


def make_petition(env, threshold=2, title="Fix the park lights"):
    env.sender(CREATOR)
    return env.c.create_petition(title, "Repair all broken street lights", threshold)


def test_create_returns_id_and_open_record(pq):
    pid = make_petition(pq, threshold=3)
    assert pid == "petition-0"
    rec = json.loads(pq.c.get_petition(pid))
    assert rec["status"] == "OPEN"
    assert rec["threshold"] == 3
    assert rec["signature_count"] == 0
    assert rec["certified_count"] == 0
    assert rec["creator"] == CREATOR.lower()
    assert json.loads(pq.c.get_counts()) == {
        "petition_count": 1,
        "total_signatures": 0,
    }


def test_create_title_validation(pq):
    pq.sender(CREATOR)
    with pytest.raises(Exception, match="INVALID_INPUT"):
        pq.c.create_petition("", "goal", 2)
    with pytest.raises(Exception, match="INVALID_INPUT"):
        pq.c.create_petition("t" * 201, "goal", 2)


def test_create_goal_validation(pq):
    pq.sender(CREATOR)
    with pytest.raises(Exception, match="INVALID_INPUT"):
        pq.c.create_petition("title", "", 2)


def test_create_threshold_validation(pq):
    pq.sender(CREATOR)
    with pytest.raises(Exception, match="INVALID_INPUT"):
        pq.c.create_petition("t", "g", 1)
    with pytest.raises(Exception, match="INVALID_INPUT"):
        pq.c.create_petition("t", "g", 1001)
    assert pq.c.create_petition("t", "g", 2) == "petition-0"
    assert pq.c.create_petition("t", "g", 1000) == "petition-1"


def test_creator_cap_8(pq):
    pq.sender(CREATOR)
    for _ in range(8):
        pq.c.create_petition("t", "g", 2)
    with pytest.raises(Exception, match="CREATOR_CAP"):
        pq.c.create_petition("t", "g", 2)
    pq.sender(SIGNER1)
    assert pq.c.create_petition("t", "g", 2) == "petition-8"


def test_sign_reachable_counts(pq):
    pid = make_petition(pq)
    pq.web(REACHABLE, 200, LONG_BODY)
    pq.sender(SIGNER1)
    assert pq.c.sign_petition(pid, REACHABLE) is None
    assert pq.c.get_signature_count(pid) == "1"
    assert json.loads(pq.c.get_signers(pid)) == [SIGNER1.lower()]
    assert json.loads(pq.c.get_counts())["total_signatures"] == 1
    rec = json.loads(pq.c.get_petition(pid))
    assert rec["status"] == "OPEN"
    assert rec["signature_count"] == 1


def test_sign_duplicate_rejected(pq):
    pid = make_petition(pq)
    pq.web(REACHABLE, 200, LONG_BODY)
    pq.sender(SIGNER1)
    pq.c.sign_petition(pid, REACHABLE)
    with pytest.raises(Exception, match="ALREADY_SIGNED"):
        pq.c.sign_petition(pid, REACHABLE)
    assert pq.c.get_signature_count(pid) == "1"


def test_sign_unreachable_404_fail_closed(pq):
    pid = make_petition(pq)
    pq.web(MISSING, 404, b"not found")
    pq.sender(SIGNER1)
    assert pq.c.sign_petition(pid, MISSING) is None
    assert pq.c.get_signature_count(pid) == "0"
    assert json.loads(pq.c.get_signers(pid)) == []
    assert json.loads(pq.c.get_petition(pid))["status"] == "OPEN"
    assert json.loads(pq.c.get_counts())["total_signatures"] == 0


def test_sign_unreachable_exception_fail_closed(pq):
    pid = make_petition(pq)
    pq.web_down(DOWN)
    pq.sender(SIGNER1)
    assert pq.c.sign_petition(pid, DOWN) is None
    assert pq.c.get_signature_count(pid) == "0"


def test_sign_short_body_fail_closed(pq):
    pid = make_petition(pq)
    pq.web(SHORT, 200, b"tiny")
    pq.sender(SIGNER1)
    assert pq.c.sign_petition(pid, SHORT) is None
    assert pq.c.get_signature_count(pid) == "0"


def test_threshold_flip_to_certified(pq):
    pid = make_petition(pq, threshold=2)
    pq.web(REACHABLE, 200, LONG_BODY)
    pq.sender(SIGNER1)
    pq.c.sign_petition(pid, REACHABLE)
    pq.sender(SIGNER2)
    pq.c.sign_petition(pid, REACHABLE)
    rec = json.loads(pq.c.get_petition(pid))
    assert rec["status"] == "CERTIFIED"
    assert rec["signature_count"] == 2
    assert rec["certified_count"] == 2
    assert pq.c.get_signature_count(pid) == "2"


def test_sign_on_certified_rejected(pq):
    pid = make_petition(pq, threshold=2)
    pq.web(REACHABLE, 200, LONG_BODY)
    pq.sender(SIGNER1)
    pq.c.sign_petition(pid, REACHABLE)
    pq.sender(SIGNER2)
    pq.c.sign_petition(pid, REACHABLE)
    pq.sender(SIGNER3)
    with pytest.raises(Exception, match="INVALID_STATUS"):
        pq.c.sign_petition(pid, REACHABLE)


def test_sign_missing_petition(pq):
    pq.web(REACHABLE, 200, LONG_BODY)
    pq.sender(SIGNER1)
    with pytest.raises(Exception, match="NOT_FOUND"):
        pq.c.sign_petition("petition-99", REACHABLE)


def test_sign_bad_url(pq):
    pid = make_petition(pq)
    pq.sender(SIGNER1)
    with pytest.raises(Exception, match="INVALID_INPUT"):
        pq.c.sign_petition(pid, "ftp://example.com/x")
    with pytest.raises(Exception, match="INVALID_INPUT"):
        pq.c.sign_petition(pid, "")


def test_views_on_missing(pq):
    assert pq.c.get_petition("petition-99") == ""
    assert pq.c.get_signature_count("petition-99") == "0"
    assert pq.c.get_signers("petition-99") == "[]"
    assert json.loads(pq.c.get_counts()) == {
        "petition_count": 0,
        "total_signatures": 0,
    }


def test_signer_stored_lowercase_and_case_insensitive_duplicate(pq):
    pid = make_petition(pq)
    pq.web(REACHABLE, 200, LONG_BODY)
    pq.sender(SIGNER1)
    pq.c.sign_petition(pid, REACHABLE)
    assert json.loads(pq.c.get_signers(pid)) == [SIGNER1.lower()]
    pq.sender(SIGNER1.lower())
    with pytest.raises(Exception, match="ALREADY_SIGNED"):
        pq.c.sign_petition(pid, REACHABLE)
