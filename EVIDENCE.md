# PetitionQuorum — Evidence

## Deployment

- Network: Stable Studionet, chain ID 61999, RPC `https://studio.genlayer.com/api`
- Contract: `0xeb32b2618A70122853bC8665aeaF8e512f814FAa`
- Explorer: https://explorer-studio.genlayer.com/address/0xeb32b2618A70122853bC8665aeaF8e512f814FAa
- Deploy tx: `0xd298519172c6d75dbf147f8b9e4d427dbaafbadbc941c209847f188c8cdafb11` (FINALIZED, SUCCESS)
- Source: `contracts/petitionquorum.py`
- Source SHA256: `5579f43edb45a5c0de37306bc82add94c4c455fb2eb9aaa930a6c4a49c5d4c6b`
- The SHA256 above matches the deployed source file byte-for-byte (confirmed by an independent read of the repository file after deployment).

## Verification loop (on-chain, FINALIZED)

The loop deployed a fresh contract, ran the full flow, and read back state after every step. All transactions reached FINALIZED.

| Step | Tx | Result | Note |
| --- | --- | --- | --- |
| deploy | `0xd298519172c6d75dbf147f8b9e4d427dbaafbadbc941c209847f188c8cdafb11` | SUCCESS | |
| create-A (threshold 2) | `0x48c50063de0f164f6baa452f0b407ee3b051bbcaf0f8546a3d85c8f0d4f5711b` | SUCCESS | petition-0 |
| create-B (threshold 3) | `0xc24308a4905b098a3b4c5c764716eec642da9dcc1b31f05ffc99b8e759e33dfe` | SUCCESS | petition-1 |
| sign-A-1 (reachable evidence) | `0xdc4840310a310d632029340420149e63c90ae5128c3c085392aaadc82bdec93a` | SUCCESS | count 1, OPEN |
| sign-A-duplicate | `0xa1c35e2e11850dec5381f96df4aec2cbe3f2980ce6111eb5f184d6b275a1e3b0` | ERROR | `ALREADY_SIGNED`; count stays 1 |
| sign-A-unreachable (404 evidence) | `0xef32c694bb4e56c89df3e4575d9f64444b40c9c185928b19ce4abd737464ebb5` | SUCCESS | fail-closed: signature not counted, count stays 1, OPEN |
| sign-A-2 (reachable evidence) | `0xcebcf4216cecb5659997cc77cb0abfab607c2caa0a57d920e309bae5ab367862` | SUCCESS | count 2, **CERTIFIED**, certified_count 2 |
| sign-A-certified | `0xd899cf40c487f95950b8f9c842fce826d0bf075d411ca260a402915f3906c4eb` | ERROR | `INVALID_STATUS`; CERTIFIED is terminal |
| sign-missing (petition-99) | `0xd051a40fb0081f7c9891a6c6d7d3761bc7d2ed072276c743e070a3013840b97c` | ERROR | `NOT_FOUND` |
| create-cap-2 … create-cap-7 (6 more) | `0xa9f3cccd11deb8f0a45278751ac0fd950207c824941fb89dc181919c018c8b13`, `0x043827144a94d24d0a5c14b59e6af314928d2678f67c24b32b45dbedb18238fc`, `0xc2bfb6101d1444e617a526efbad97eddf4bdd7af3cd2297283f06f81b04002de`, `0xc127713d95bc51bd67a176e05942eda78600c3054e678e2f82e82b19860d9579`, `0xc090ea3ebcff3444542c6c2b2cad0e127a024d9736bd392b9346bd4a1025a807`, `0x43deaa9ad87a917e34038cc8dffb7e96e5f57cf99c9f6a00a301e156a446e513` | SUCCESS | creator reaches 8 petitions |
| create-cap-9th | `0xfa0d5e40d5b14777ad13b8b5eded62a678ca5ea3bc9357f743ad4e291aaceac9` | ERROR | `CREATOR_CAP` |
| create-bad-threshold (threshold 1) | `0x710d465bf88dc421e365e103b99ef5238a4c5d2a2b275e79b6e98062150f628f` | ERROR | `INVALID_INPUT` |

Final counts (independent RPC readback, separate client): `petition_count 8`, `total_signatures 2`.

Independent readbacks after the loop:

- `get_petition("petition-0")` → status `CERTIFIED`, `signature_count 2`, `certified_count 2`, threshold 2, title "Repair the park lights".
- `get_signers("petition-0")` → the two distinct signer addresses (stored lowercase, as the contract records sender addresses).
- `get_petition("petition-1")` → status `OPEN`, `signature_count 0`, threshold 3, title "Build a community garden".

## Attempt log

- Run 1: the loop's deploy transaction reached FINALIZED with an execution error. The script asserted the execution result before checkpointing the deploy hash, so the hash was not recorded and the ephemeral funder key was lost with the process. The failure cause was undiagnosed at the time.
- Run 2: with deploy diagnostics added, the receipt error was `no contract defined` from the on-chain runner. Root cause: the contract class did not subclass `gl.Contract`, so the runner found no registered contract after import. Fixed by declaring `class PetitionQuorum(gl.Contract):`. The run 2 deploy hash was not preserved (the checkpoint was overwritten by the successful run).
- Run 3: full loop verified (table above). The two failed deploys created no contract; only the run 3 address is live.

## Local test suites

- Stand-in suite (stubbed `genlayer` module, in-process contract semantics): 16/16 passed.
- Direct GenVM suite (real GenVM, mocked web responses): 10/10 passed.
- `genvm-lint check` on `contracts/petitionquorum.py`: lint and validation passed (6 methods: 4 view, 2 write).

## Scope

- Signatures are counted on evidence reachability (HTTP 200 and body ≥ 100 chars, agreed by validators), not on a judgment of the petition's content.
- No funds, no escrow, no withdrawals, no signature editing; CERTIFIED is terminal.
- Evidence URLs that are unreachable, non-200, or raise an error fail closed: the signature is not counted and the petition stays open. Validators that disagree on reachability produce an execution error, and the signature can be retried.
