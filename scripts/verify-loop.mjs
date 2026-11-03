// PetitionQuorum verify loop: deploys fresh, then proves the full loop
// with independent RPC readbacks after every step. Run from repo root:
//   node scripts/verify-loop.mjs
// Checkpoints evidence/loop-flow.json after EVERY step; writes
// evidence/deployment.json and sets verified:true only at full completion.
// Ephemeral script accounts only; keys live in memory, never on disk.

import { createClient, createAccount } from 'genlayer-js';
import { studionet } from 'genlayer-js/chains';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const RPC = 'https://studio.genlayer.com/api';
const REACHABLE_URL = 'https://example.com';
const UNREACHABLE_URL = 'https://example.com/this-page-does-not-exist-xyz-404';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const sha256 = (s) => crypto.createHash('sha256').update(s).digest('hex');

async function rpcCall(method, params) {
  const res = await fetch(RPC, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ jsonrpc: '2.0', id: 1, method, params }),
  });
  const text = await res.text();
  let json;
  try {
    json = JSON.parse(text);
  } catch {
    throw new Error('RPC non-JSON response: ' + text.slice(0, 120));
  }
  if (json.error) throw new Error('RPC error: ' + JSON.stringify(json.error));
  return json.result;
}

async function fund(address, weiNumber) {
  // Faucet amount is wei as a NUMBER (a string fails; 10 = 10 wei).
  await rpcCall('sim_fundAccount', [address, weiNumber]);
  for (let i = 0; i < 20; i++) {
    const bal = await rpcCall('eth_getBalance', [address, 'latest']);
    if (BigInt(bal) >= BigInt(weiNumber)) return bal;
    await sleep(3000);
  }
  throw new Error('funding timeout for ' + address);
}

// The Studionet RPC intermittently returns an HTML error page instead of
// JSON during receipt polling. Polling a known tx hash is idempotent, so
// retry the whole receipt wait through transient errors.
async function waitFinalized(client, hash) {
  let lastErr = null;
  for (let attempt = 0; attempt < 12; attempt++) {
    try {
      return await client.waitForTransactionReceipt({
        hash,
        status: 'FINALIZED',
        interval: 3000,
        retries: 200,
      });
    } catch (e) {
      lastErr = e;
      const msg = String(e?.message || e);
      const transient =
        msg.includes('<!DOCTYPE') ||
        msg.includes('not valid JSON') ||
        msg.includes('UnknownRpcError') ||
        msg.includes('eth_getTransactionByHash') ||
        msg.includes('Transaction not found');
      if (!transient) throw e;
      console.log(
        'transient RPC error while polling', hash.slice(0, 14),
        '- retrying in 15s (attempt', attempt + 1, ')',
      );
      await sleep(15000);
    }
  }
  throw lastErr;
}

function executionOf(receipt) {
  const lr = receipt?.consensus_data?.leader_receipt;
  const first = Array.isArray(lr) ? lr[0] : lr;
  const raw =
    first?.execution_result ??
    receipt?.txExecutionResultName ??
    receipt?.txExecutionResult;
  if (raw === 'SUCCESS' || raw === 'FINISHED_WITH_RETURN' || raw === 1) {
    return 'SUCCESS';
  }
  if (raw === 'ERROR' || raw === 'FINISHED_WITH_ERROR' || raw === 2) {
    return 'ERROR';
  }
  return 'UNKNOWN:' + String(raw);
}

function errorTextOf(receipt) {
  try {
    const lr = receipt?.consensus_data?.leader_receipt;
    const first = Array.isArray(lr) ? lr[0] : lr;
    const v = first?.genvm_result ?? first?.result ?? null;
    if (v === null || v === undefined) return null;
    return typeof v === 'string' ? v : JSON.stringify(v);
  } catch {
    return null;
  }
}

function assertFinalized(receipt, label) {
  const st = receipt?.status;
  const stName = receipt?.status_name || receipt?.statusName;
  if (!(st === 7 || st === '7' || stName === 'FINALIZED')) {
    throw new Error(
      label + ': not FINALIZED (status=' + st + ' name=' + stName + ')',
    );
  }
}

const flow = {
  contractAddress: null,
  deployTx: null,
  sourceSha256: null,
  verified: false,
  accounts: {},
  steps: [],
};

function saveFlow() {
  fs.mkdirSync(path.join(ROOT, 'evidence'), { recursive: true });
  fs.writeFileSync(
    path.join(ROOT, 'evidence', 'loop-flow.json'),
    JSON.stringify(flow, null, 2) + '\n',
  );
}

let client;
let address;

async function writeStep(account, label, functionName, args, expected) {
  const ret = await client.writeContract({
    account,
    address,
    functionName,
    args,
    value: 0n,
  });
  const hash = typeof ret === 'string' ? ret : ret.hash;
  const receipt = await waitFinalized(client, hash);
  assertFinalized(receipt, label);
  const exec = executionOf(receipt);
  if (exec !== expected) {
    throw new Error(
      label + ': expected ' + expected + ', got ' + exec + ' (tx ' + hash + ')',
    );
  }
  flow.steps.push({
    label,
    hash,
    executionResult: exec,
    errorText: errorTextOf(receipt),
  });
  saveFlow();
  console.log(label, hash, exec);
  return hash;
}

async function readView(functionName, args) {
  let lastErr;
  for (let i = 0; i < 6; i++) {
    try {
      return await client.readContract({ address, functionName, args });
    } catch (e) {
      lastErr = e;
      await sleep(5000);
    }
  }
  throw lastErr;
}

function assertEq(actual, expected, what) {
  if (actual !== expected) {
    throw new Error(
      what + ': expected ' + JSON.stringify(expected) +
      ', got ' + JSON.stringify(actual),
    );
  }
}

async function main() {
  const code = fs.readFileSync(
    path.join(ROOT, 'contracts', 'petitionquorum.py'), 'utf8',
  );
  flow.sourceSha256 = sha256(code);
  client = createClient({ chain: studionet });

  const creator = createAccount();
  const signer1 = createAccount();
  const signer2 = createAccount();
  const signer3 = createAccount();
  const outsider = createAccount();
  flow.accounts = {
    creator: creator.address,
    signer1: signer1.address,
    signer2: signer2.address,
    signer3: signer3.address,
    outsider: outsider.address,
  };

  // Fund each account 1 GEN (faucet number literal, exact in JSON).
  for (const a of [creator, signer1, signer2, signer3, outsider]) {
    await fund(a.address, 1000000000000000000);
  }
  console.log('accounts funded');

  // Deploy fresh.
  const deployHash = await client.deployContract({ account: creator, code });
  const deployReceipt = await waitFinalized(client, deployHash);
  // Checkpoint the deploy hash BEFORE asserting, so a failed deploy stays
  // diagnosable instead of vanishing with the process.
  flow.deployTx = deployHash;
  flow.steps.push({
    label: 'deploy',
    hash: deployHash,
    executionResult: executionOf(deployReceipt),
    errorText: errorTextOf(deployReceipt),
  });
  saveFlow();
  console.log('deploy receipt:', JSON.stringify({
    status: deployReceipt?.status,
    statusName: deployReceipt?.status_name || deployReceipt?.statusName,
    execution: executionOf(deployReceipt),
    errorText: errorTextOf(deployReceipt),
  }));
  assertFinalized(deployReceipt, 'deploy');
  assertEq(executionOf(deployReceipt), 'SUCCESS', 'deploy execution');
  address =
    deployReceipt?.data?.contract_address || deployReceipt?.to_address;
  if (!address) {
    throw new Error('deploy receipt has no contract address: ' +
      JSON.stringify(deployReceipt).slice(0, 500));
  }
  flow.contractAddress = address;
  saveFlow();
  console.log('deploy', deployHash, 'SUCCESS', address);

  // Sanity: fresh contract reads back empty.
  assertEq(
    JSON.stringify(JSON.parse(await readView('get_counts', []))),
    JSON.stringify({ petition_count: 0, total_signatures: 0 }),
    'fresh counts',
  );

  // 1. Create petition A (threshold 2) -> petition-0.
  await writeStep(
    creator, 'create-A', 'create_petition',
    ['Repair the park lights', 'Fix all broken street lights on Maple Street', 2],
    'SUCCESS',
  );
  let rec = JSON.parse(await readView('get_petition', ['petition-0']));
  assertEq(rec.status, 'OPEN', 'A status after create');
  assertEq(rec.threshold, 2, 'A threshold');
  assertEq(rec.signature_count, 0, 'A count after create');
  assertEq(rec.creator, creator.address.toLowerCase(), 'A creator');

  // 2. Create petition B (threshold 3) -> petition-1.
  await writeStep(
    creator, 'create-B', 'create_petition',
    ['Build a community garden', 'Convert the vacant lot into a garden', 3],
    'SUCCESS',
  );
  assertEq(
    JSON.stringify(JSON.parse(await readView('get_counts', []))),
    JSON.stringify({ petition_count: 2, total_signatures: 0 }),
    'counts after two creates',
  );

  // 3. Sign A by signer1, reachable evidence -> counted, still OPEN.
  await writeStep(
    signer1, 'sign-A-1', 'sign_petition', ['petition-0', REACHABLE_URL],
    'SUCCESS',
  );
  assertEq(await readView('get_signature_count', ['petition-0']), '1', 'A count after sign 1');
  assertEq(
    JSON.stringify(JSON.parse(await readView('get_signers', ['petition-0']))),
    JSON.stringify([signer1.address.toLowerCase()]),
    'A signers after sign 1',
  );
  rec = JSON.parse(await readView('get_petition', ['petition-0']));
  assertEq(rec.status, 'OPEN', 'A status after sign 1');

  // 4. Duplicate sign A by signer1 -> rejected, count unchanged.
  await writeStep(
    signer1, 'sign-A-duplicate', 'sign_petition', ['petition-0', REACHABLE_URL],
    'ERROR',
  );
  assertEq(await readView('get_signature_count', ['petition-0']), '1', 'A count after duplicate');

  // 5. Sign A by signer2, unreachable evidence (404) -> fail-closed success.
  await writeStep(
    signer2, 'sign-A-unreachable', 'sign_petition', ['petition-0', UNREACHABLE_URL],
    'SUCCESS',
  );
  assertEq(await readView('get_signature_count', ['petition-0']), '1', 'A count after unreachable');
  rec = JSON.parse(await readView('get_petition', ['petition-0']));
  assertEq(rec.status, 'OPEN', 'A status after unreachable');

  // 6. Sign A by signer2, reachable evidence -> count 2 -> CERTIFIED.
  await writeStep(
    signer2, 'sign-A-2', 'sign_petition', ['petition-0', REACHABLE_URL],
    'SUCCESS',
  );
  rec = JSON.parse(await readView('get_petition', ['petition-0']));
  assertEq(rec.status, 'CERTIFIED', 'A status after threshold');
  assertEq(rec.signature_count, 2, 'A count at certification');
  assertEq(rec.certified_count, 2, 'A certified count');
  assertEq(
    JSON.stringify(JSON.parse(await readView('get_signers', ['petition-0']))),
    JSON.stringify([signer1.address.toLowerCase(), signer2.address.toLowerCase()]),
    'A signers at certification',
  );

  // 7. Sign CERTIFIED A by signer3 -> rejected.
  await writeStep(
    signer3, 'sign-A-certified', 'sign_petition', ['petition-0', REACHABLE_URL],
    'ERROR',
  );
  assertEq(await readView('get_signature_count', ['petition-0']), '2', 'A count after certified sign');

  // 8. Sign missing petition -> rejected.
  await writeStep(
    signer3, 'sign-missing', 'sign_petition', ['petition-99', REACHABLE_URL],
    'ERROR',
  );

  // 9. Creator cap: creator already has 2 petitions; create 6 more (2..7).
  for (let i = 2; i <= 7; i++) {
    await writeStep(
      creator, 'create-cap-' + i, 'create_petition',
      ['Petition ' + i, 'Goal ' + i, 2],
      'SUCCESS',
    );
  }
  // 9th create -> rejected.
  await writeStep(
    creator, 'create-cap-9th', 'create_petition',
    ['Petition 9', 'Goal 9', 2],
    'ERROR',
  );

  // 10. Invalid threshold by a fresh creator -> rejected.
  await writeStep(
    outsider, 'create-bad-threshold', 'create_petition',
    ['Bad threshold', 'Goal', 1],
    'ERROR',
  );

  // Final readbacks.
  const counts = JSON.parse(await readView('get_counts', []));
  assertEq(counts.petition_count, 8, 'final petition count');
  assertEq(counts.total_signatures, 2, 'final total signatures');
  rec = JSON.parse(await readView('get_petition', ['petition-0']));
  assertEq(rec.status, 'CERTIFIED', 'final A status');
  const recB = JSON.parse(await readView('get_petition', ['petition-1']));
  assertEq(recB.status, 'OPEN', 'final B status');
  assertEq(recB.signature_count, 0, 'final B count');

  flow.verified = true;
  flow.finalCounts = counts;
  saveFlow();
  fs.writeFileSync(
    path.join(ROOT, 'evidence', 'deployment.json'),
    JSON.stringify(
      {
        contractAddress: address,
        network: 'studionet',
        chainId: 61999,
        sourceSha256: flow.sourceSha256,
        deployTx: deployHash,
        verified: true,
        counts,
      },
      null,
      2,
    ) + '\n',
  );
  console.log('VERIFIED. contract:', address);
  console.log('flow: evidence/loop-flow.json, deployment: evidence/deployment.json');
}

main().catch((e) => {
  console.error('LOOP FAILED:', e);
  try {
    saveFlow();
  } catch {}
  process.exit(1);
});
