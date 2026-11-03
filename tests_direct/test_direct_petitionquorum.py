"""Direct (real GenVM) tests for PetitionQuorum.

These prove the real-VM nondet path: strict_eq consensus over a mocked
web fetch, plus guards and state transitions. The exception fail-closed
path is covered by stand-in tests (mock_web cannot simulate a fetch
exception); settle-style balance assertions do not apply (no funds).
"""

import json

CONTRACT = "contracts/petitionquorum.py"
OK_URL = "https://example.com/evidence-ok"
MISSING_URL = "https://example.com/evidence-missing"
SHORT_URL = "https://example.com/evidence-short"
LONG_BODY = "x" * 200


def addr_str(a):
    # Direct addresses arrive as raw bytes in this harness; the contract
    # stores str(sender_address).lower(), i.e. the lowercase hex form.
    if isinstance(a, (bytes, bytearray)):
        return "0x" + bytes(a).hex()
    return str(a).lower()


def deploy(direct_deploy):
    return direct_deploy(CONTRACT)


def test_direct_create_and_views(direct_vm, direct_deploy, direct_alice):
    c = deploy(direct_deploy)
    direct_vm.sender = direct_alice
    c.create_petition("Fix the park lights", "Repair all broken lights", 2)
    rec = json.loads(c.get_petition("petition-0"))
    assert rec["status"] == "OPEN"
    assert rec["threshold"] == 2
    assert rec["signature_count"] == 0
    assert rec["creator"] == addr_str(direct_alice)
    assert c.get_signature_count("petition-0") == "0"
    assert c.get_signers("petition-0") == "[]"
    assert json.loads(c.get_counts()) == {
        "petition_count": 1,
        "total_signatures": 0,
    }


def test_direct_create_validation(direct_vm, direct_deploy, direct_alice):
    c = deploy(direct_deploy)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("INVALID_INPUT"):
        c.create_petition("t", "g", 1)
    with direct_vm.expect_revert("INVALID_INPUT"):
        c.create_petition("", "g", 2)


def test_direct_creator_cap(direct_vm, direct_deploy, direct_alice):
    c = deploy(direct_deploy)
    direct_vm.sender = direct_alice
    for _ in range(8):
        c.create_petition("t", "g", 2)
    with direct_vm.expect_revert("CREATOR_CAP"):
        c.create_petition("t", "g", 2)


def test_direct_sign_reachable(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = deploy(direct_deploy)
    direct_vm.sender = direct_alice
    c.create_petition("Fix the park lights", "Repair all broken lights", 2)
    direct_vm.mock_web(r"example\.com/evidence-ok", {
        "method": "GET", "status": 200, "body": LONG_BODY,
    })
    direct_vm.sender = direct_bob
    c.sign_petition("petition-0", OK_URL)
    assert c.get_signature_count("petition-0") == "1"
    assert json.loads(c.get_signers("petition-0")) == [addr_str(direct_bob)]
    assert json.loads(c.get_counts())["total_signatures"] == 1


def test_direct_sign_duplicate(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = deploy(direct_deploy)
    direct_vm.sender = direct_alice
    c.create_petition("t", "g", 2)
    direct_vm.mock_web(r"example\.com/evidence-ok", {
        "method": "GET", "status": 200, "body": LONG_BODY,
    })
    direct_vm.sender = direct_bob
    c.sign_petition("petition-0", OK_URL)
    with direct_vm.expect_revert("ALREADY_SIGNED"):
        c.sign_petition("petition-0", OK_URL)
    assert c.get_signature_count("petition-0") == "1"


def test_direct_sign_unreachable_404_fail_closed(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    c = deploy(direct_deploy)
    direct_vm.sender = direct_alice
    c.create_petition("t", "g", 2)
    direct_vm.mock_web(r"example\.com/evidence-missing", {
        "method": "GET", "status": 404, "body": "not found",
    })
    direct_vm.sender = direct_bob
    c.sign_petition("petition-0", MISSING_URL)
    assert c.get_signature_count("petition-0") == "0"
    assert c.get_signers("petition-0") == "[]"
    assert json.loads(c.get_petition("petition-0"))["status"] == "OPEN"


def test_direct_sign_short_body_fail_closed(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    c = deploy(direct_deploy)
    direct_vm.sender = direct_alice
    c.create_petition("t", "g", 2)
    direct_vm.mock_web(r"example\.com/evidence-short", {
        "method": "GET", "status": 200, "body": "tiny",
    })
    direct_vm.sender = direct_bob
    c.sign_petition("petition-0", SHORT_URL)
    assert c.get_signature_count("petition-0") == "0"


def test_direct_threshold_flip(
    direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie
):
    c = deploy(direct_deploy)
    direct_vm.sender = direct_alice
    c.create_petition("t", "g", 2)
    direct_vm.mock_web(r"example\.com/evidence-ok", {
        "method": "GET", "status": 200, "body": LONG_BODY,
    })
    direct_vm.sender = direct_bob
    c.sign_petition("petition-0", OK_URL)
    direct_vm.sender = direct_charlie
    c.sign_petition("petition-0", OK_URL)
    rec = json.loads(c.get_petition("petition-0"))
    assert rec["status"] == "CERTIFIED"
    assert rec["signature_count"] == 2
    assert rec["certified_count"] == 2


def test_direct_sign_on_certified(
    direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie, direct_owner
):
    c = deploy(direct_deploy)
    direct_vm.sender = direct_alice
    c.create_petition("t", "g", 2)
    direct_vm.mock_web(r"example\.com/evidence-ok", {
        "method": "GET", "status": 200, "body": LONG_BODY,
    })
    direct_vm.sender = direct_bob
    c.sign_petition("petition-0", OK_URL)
    direct_vm.sender = direct_charlie
    c.sign_petition("petition-0", OK_URL)
    direct_vm.sender = direct_owner
    with direct_vm.expect_revert("INVALID_STATUS"):
        c.sign_petition("petition-0", OK_URL)


def test_direct_sign_not_found(direct_vm, direct_deploy, direct_bob):
    c = deploy(direct_deploy)
    direct_vm.mock_web(r"example\.com/evidence-ok", {
        "method": "GET", "status": 200, "body": LONG_BODY,
    })
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert("NOT_FOUND"):
        c.sign_petition("petition-99", OK_URL)
