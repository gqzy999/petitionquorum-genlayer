// Standalone deploy of PetitionQuorum (no loop). Run from repo root:
//   node scripts/deploy.mjs
// Writes evidence/deployment.json (verified:false). For the full proven
// loop, run scripts/verify-loop.mjs instead.

import { createClient, createAccount } from 'genlayer-js';
import { studionet } from 'genlayer-js/chains';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const RPC = 'https://studio.genlayer.com/api';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function rpcCall(method, params) {
  const res = await fetch(RPC, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ jsonrpc: '2.0', id: 1, method, params }),
  });
  const json = JSON.parse(await res.text());
  if (json.error) throw new Error('RPC error: ' + JSON.stringify(json.error));
  return json.result;
}

const code = fs.readFileSync(
  path.join(ROOT, 'contracts', 'petitionquorum.py'), 'utf8',
);
const sourceSha256 = crypto.createHash('sha256').update(code).digest('hex');
const client = createClient({ chain: studionet });
const deployer = createAccount();
await rpcCall('sim_fundAccount', [deployer.address, 1000000000000000000]);
for (let i = 0; i < 20; i++) {
  const bal = await rpcCall('eth_getBalance', [deployer.address, 'latest']);
  if (BigInt(bal) >= 1000000000000000000n) break;
  await sleep(3000);
}
const hash = await client.deployContract({ account: deployer, code });
const receipt = await client.waitForTransactionReceipt({
  hash,
  status: 'FINALIZED',
  interval: 3000,
  retries: 200,
});
const address = receipt?.data?.contract_address || receipt?.to_address;
console.log('deploy tx:', hash);
console.log('contract:', address);
console.log('status:', receipt?.status, receipt?.status_name || receipt?.statusName);
fs.mkdirSync(path.join(ROOT, 'evidence'), { recursive: true });
fs.writeFileSync(
  path.join(ROOT, 'evidence', 'deployment.json'),
  JSON.stringify(
    {
      contractAddress: address,
      network: 'studionet',
      chainId: 61999,
      sourceSha256,
      deployTx: hash,
      verified: false,
    },
    null,
    2,
  ) + '\n',
);
