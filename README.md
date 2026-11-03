# PetitionQuorum

**Live contract (Stable Studionet, chain ID 61999):** https://explorer-studio.genlayer.com/address/0xeb32b2618A70122853bC8665aeaF8e512f814FAa

PetitionQuorum certifies petitions by quorum: when the number of verified signatures reaches a petition's threshold, its status flips to CERTIFIED. Signatures are verified by agreement that the signer's evidence URL is reachable — a collective-action quorum, not a policy gate, not a verdict escrow, not a record registry.

## How it works

- `create_petition(title, goal, threshold)` — anyone creates a petition with a signature threshold (≥ 2, ≤ 1000). Per-creator cap: 8 petitions. Title 1–200 chars.
- `sign_petition(petition_id, evidence_url)` — one signature per signer; the same signer cannot sign twice. Validators fetch the evidence URL and agree it is reachable (HTTP 200 and body ≥ 100 chars). A reachable evidence URL counts as a valid signature. Unreachable, non-200, or erroring evidence fails closed: the signature is not counted and the petition stays open. This is reachability agreement, not a judgment on the petition's content.
- When valid signatures reach the threshold, the petition status flips to CERTIFIED (terminal, with the certified signature count recorded). Below the threshold it stays OPEN. Withdrawing or editing signatures is not supported.
- Views: `get_petition`, `get_signature_count`, `get_signers`, `get_counts`.

No funds, no escrow, no floats. Evolving state: signature counts and CERTIFIED flips.

## Deployment

- Contract: `0xeb32b2618A70122853bC8665aeaF8e512f814FAa`
- Deploy tx: `0xd298519172c6d75dbf147f8b9e4d427dbaafbadbc941c209847f188c8cdafb11` (FINALIZED, SUCCESS)
- Source: `contracts/petitionquorum.py` (SHA256 `5579f43edb45a5c0de37306bc82add94c4c455fb2eb9aaa930a6c4a49c5d4c6b`)

## Verification

See `EVIDENCE.md` for the full on-chain loop (17 FINALIZED transactions: create, valid signatures counting, duplicate-signature rejection, unreachable-evidence fail-closed, threshold flip to CERTIFIED, creator cap, threshold bounds, independent readbacks after every step) and `evidence.json` for the machine-readable record.

Local checks:

```sh
python -m venv .venv && .venv/bin/pip install genlayer-py genlayer-test genvm-linter pytest
.venv/bin/pytest tests tests_direct
.venv/bin/genvm-lint check contracts/petitionquorum.py
```

## Scope

- Evidence reachability is the only thing validators agree on; the petition's content is not judged on-chain.
- A signature whose evidence is unreachable is not counted, and the petition stays open; validators that disagree on reachability produce an execution error, and the signature can be retried.
- CERTIFIED is terminal; no further signatures are accepted once a petition is certified.
