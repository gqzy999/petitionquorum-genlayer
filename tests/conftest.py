"""Stand-in test harness for PetitionQuorum.

Builds a fake ``genlayer`` module (types + gl namespace) and loads the
real contract file against it. No GenVM involved: consensus is faked by
executing the nondet function directly, so these tests prove the state
machine, guards, and storage handling only. The real-VM nondet path is
proven by tests_direct/ and the Studionet loop.
"""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

CONTRACT_PATH = Path(__file__).resolve().parent.parent / "contracts" / "petitionquorum.py"


class TreeMap(dict):
    def __class_getitem__(cls, item):
        return cls


class Address(str):
    pass


class _Lazy:
    def __init__(self, fn):
        self._fn = fn

    def get(self):
        return self._fn()


class _Response:
    def __init__(self, status, body):
        self.status = status
        self.body = body


class _Public:
    @staticmethod
    def view(f):
        return f

    @staticmethod
    def write(f):
        return f


def allow_storage(cls):
    return cls


class _Message:
    def __init__(self):
        self.sender_address = "0x0000000000000000000000000000000000000000"


class _Web:
    def __init__(self, mocks):
        self._mocks = mocks

    def get(self, url):
        # Mirrors the real SDK: web.get is eager, returns the Response.
        if url not in self._mocks:
            raise RuntimeError("no web mock for " + url)
        mocked = self._mocks[url]
        if isinstance(mocked, Exception):
            raise mocked
        status, body = mocked
        return _Response(status, body)


class _Nondet:
    def __init__(self, mocks):
        self.web = _Web(mocks)


class _EqPrinciple:
    @staticmethod
    def strict_eq(fn):
        # Mirrors the real SDK: strict_eq is eager (its @_lazy_api wrapper
        # already resolves), so it returns the value, not a Lazy.
        return fn()


class _ContractBase:
    pass


class _Gl:
    def __init__(self, mocks):
        self.public = _Public()
        self.message = _Message()
        self.nondet = _Nondet(mocks)
        self.eq_principle = _EqPrinciple()
        self.Contract = _ContractBase


def build_stub():
    mocks = {}
    gl = _Gl(mocks)
    mod = types.ModuleType("genlayer")
    mod.__all__ = ["gl", "Address", "TreeMap", "u32", "u256", "allow_storage"]
    mod.gl = gl
    mod.Address = Address
    mod.TreeMap = TreeMap
    mod.u32 = int
    mod.u256 = int
    mod.allow_storage = allow_storage
    return mod, gl, mocks


def load_contract(stub):
    sys.modules["genlayer"] = stub
    spec = importlib.util.spec_from_file_location(
        "petitionquorum_under_test", CONTRACT_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["petitionquorum_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def pq():
    stub, gl, mocks = build_stub()
    mod = load_contract(stub)
    contract = mod.PetitionQuorum()
    contract.petitions = TreeMap()
    contract.petition_index = TreeMap()
    contract.creator_counts = TreeMap()
    contract.signatures = TreeMap()
    contract.signers = TreeMap()

    class Env:
        def __init__(self):
            self.c = contract
            self.gl = gl
            self.mocks = mocks

        def sender(self, addr):
            gl.message.sender_address = addr

        def web(self, url, status, body):
            mocks[url] = (status, body)

        def web_down(self, url):
            mocks[url] = RuntimeError("connection failed")

    env = Env()
    yield env
    sys.modules.pop("genlayer", None)
    sys.modules.pop("petitionquorum_under_test", None)


CREATOR = "0x5B38Da6a701c568545dCfcB03FcB875f56beddC4"
SIGNER1 = "0xAb8483F64d9C6d1EcF9b849Ae677dD3315835cb2"
SIGNER2 = "0x4B20993Bc481177ec7E8f571ceCaE8A71cD0a9"
SIGNER3 = "0x78731D3Ca6b7E34aC0F824c42a7cC18A495cabaB"

REACHABLE = "https://example.com/evidence-ok"
MISSING = "https://example.com/evidence-missing"
DOWN = "https://example.com/evidence-down"
SHORT = "https://example.com/evidence-short"
