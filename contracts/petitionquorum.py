# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
import json
from genlayer import *


def _check_url(url: str) -> str:
    try:
        resp = gl.nondet.web.get(url)
        body = resp.body
        if resp.status == 200 and body is not None and len(body) >= 100:
            return "reachable"
        return "unreachable"
    except Exception:
        return "unreachable"


@allow_storage
class PetitionQuorum(gl.Contract):
    petitions: TreeMap[str, str]
    petition_index: TreeMap[str, str]
    petition_count: u32
    creator_counts: TreeMap[str, str]
    signatures: TreeMap[str, str]
    signers: TreeMap[str, str]
    total_signatures: u32

    def __init__(self):
        self.petition_count = u32(0)
        self.total_signatures = u32(0)

    @gl.public.write
    def create_petition(self, title: str, goal: str, threshold: int) -> str:
        if not isinstance(title, str) or len(title) < 1 or len(title) > 200:
            raise Exception("INVALID_INPUT")
        if not isinstance(goal, str) or len(goal) < 1 or len(goal) > 2000:
            raise Exception("INVALID_INPUT")
        try:
            threshold = int(threshold)
        except Exception:
            raise Exception("INVALID_INPUT")
        if threshold < 2 or threshold > 1000:
            raise Exception("INVALID_INPUT")
        sender = str(gl.message.sender_address).lower()
        raw_created = self.creator_counts.get(sender)
        created = int(raw_created) if raw_created is not None else 0
        if created >= 8:
            raise Exception("CREATOR_CAP")
        petition_id = "petition-" + str(int(self.petition_count))
        record = {
            "petition_id": petition_id,
            "title": title,
            "goal": goal,
            "threshold": threshold,
            "creator": sender,
            "status": "OPEN",
            "signature_count": 0,
            "certified_count": 0,
        }
        self.petitions[petition_id] = json.dumps(record)
        self.petition_index[str(int(self.petition_count))] = petition_id
        self.petition_count = u32(int(self.petition_count) + 1)
        self.creator_counts[sender] = str(created + 1)
        return petition_id

    @gl.public.write
    def sign_petition(self, petition_id: str, evidence_url: str) -> None:
        raw = self.petitions.get(petition_id)
        if raw is None:
            raise Exception("NOT_FOUND")
        if not isinstance(evidence_url, str) or len(evidence_url) < 1 or len(evidence_url) > 2000:
            raise Exception("INVALID_INPUT")
        if not evidence_url.startswith("http://") and not evidence_url.startswith("https://"):
            raise Exception("INVALID_INPUT")
        record = json.loads(raw)
        if record["status"] == "CERTIFIED":
            raise Exception("INVALID_STATUS")
        sender = str(gl.message.sender_address).lower()
        sig_key = petition_id + "|" + sender
        if self.signatures.get(sig_key) is not None:
            raise Exception("ALREADY_SIGNED")
        def check():
            return _check_url(evidence_url)

        status = gl.eq_principle.strict_eq(check)
        if status != "reachable":
            return None
        self.signatures[sig_key] = json.dumps(
            {
                "petition_id": petition_id,
                "signer": sender,
                "evidence_url": evidence_url,
            }
        )
        raw_signers = self.signers.get(petition_id)
        signer_list = json.loads(raw_signers) if raw_signers is not None else []
        signer_list.append(sender)
        self.signers[petition_id] = json.dumps(signer_list)
        count = int(record["signature_count"]) + 1
        record["signature_count"] = count
        if count >= int(record["threshold"]):
            record["status"] = "CERTIFIED"
            record["certified_count"] = count
        self.petitions[petition_id] = json.dumps(record)
        self.total_signatures = u32(int(self.total_signatures) + 1)
        return None

    @gl.public.view
    def get_petition(self, petition_id: str) -> str:
        raw = self.petitions.get(petition_id)
        if raw is None:
            return ""
        return raw

    @gl.public.view
    def get_signature_count(self, petition_id: str) -> str:
        raw = self.petitions.get(petition_id)
        if raw is None:
            return "0"
        return str(int(json.loads(raw)["signature_count"]))

    @gl.public.view
    def get_signers(self, petition_id: str) -> str:
        raw = self.signers.get(petition_id)
        if raw is None:
            return "[]"
        return raw

    @gl.public.view
    def get_counts(self) -> str:
        return json.dumps(
            {
                "petition_count": int(self.petition_count),
                "total_signatures": int(self.total_signatures),
            }
        )
