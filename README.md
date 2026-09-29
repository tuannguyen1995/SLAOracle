# SLAOracle: Autonomous Cloud & RPC SLA Insurance Protocol

> **Track:** Builder Track — Intelligent Contracts  
> **Network:** GenLayer studionet (Chain ID: `61999` / `0xF1EF`)  
> **Target Environment:** [GenLayer Studio](https://studio.genlayer.com)  
> **Execution Engine:** GenVM / Optimistic Democracy Semantic Consensus  
> **Contract Source:** [`contracts/sla_oracle.py`](contracts/sla_oracle.py)  

---

## 1. Deployment & Live Network Evidence

The SLAOracle Intelligent Contract is deployed and verified on GenLayer studionet:

- **Contract Address:** `0xF2995aEf0B7AFd222B34dA753920FbcC45623334`
- **Deployment Network:** `studionet`
- **Execution Environment:** GenVM / Optimistic Democracy Semantic Consensus
- **Contract Source:** [`contracts/sla_oracle.py`](contracts/sla_oracle.py)
- **Deployment Record:** [`deployment.json`](deployment.json)

---

### Worked Example: Policy Underwriting & Incident Adjudication

Below is an illustrative worked example based on the contract execution flow, verified with local `gltest` suite execution and expected on-chain state transitions:

#### Step A: Infrastructure Provider Underwrites SLA Policy
- **Caller (Provider):** `0x70997970C51812dc3A010C7d01b50e0d17dc79C8`
- **Subscriber Address:** `0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC`
- **Method:** `underwrite_sla_policy(...)`
- **Arguments:**
  - `policy_id`: `"pol-node-us-east-1"`
  - `subscriber_address`: `"0x3c44cdddb6a900fa2b585dd299e03d12fa4293bc"`
  - `rpc_endpoint_url`: `"https://rpc.mainnet.example.com"`
  - `benchmark_manifest_url`: `"https://terms.example.com/sla.json"`
  - `benchmark_manifest_hash`: `"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"`
  - `max_p99_latency_ms`: `300`
  - `max_error_rate_permille`: `10` (1%)
  - `max_head_drift_blocks`: `5`
  - `coverage_duration_days`: `30`
- **Value Attached:** `5000` (5,000 GEN deposited into custodial bond)

**Policy State Query [Real Result from gltest]:**
```json
{
  "policy_id": "pol-node-us-east-1",
  "provider": "0x70997970c51812dc3a010c7d01b50e0d17dc79c8",
  "subscriber": "0x3c44cdddb6a900fa2b585dd299e03d12fa4293bc",
  "underwriting_bond": "5000",
  "status": "ACTIVE",
  "rpc_endpoint_url": "https://rpc.mainnet.example.com",
  "benchmark_manifest_url": "https://terms.example.com/sla.json",
  "benchmark_manifest_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "incident_telemetry_url": "",
  "incident_telemetry_hash": "",
  "max_p99_latency_ms": "300",
  "max_error_rate_permille": "10",
  "max_head_drift_blocks": "5",
  "verdict": "NONE",
  "rationale": "Policy underwritten and active; monitoring service metrics",
  "created_at": "1790035200",
  "challenge_ends_at": "0",
  "last_disputed_at": "0"
}
```

#### Step B: Subscriber Submits Incident Telemetry Assessment
- **Caller (Subscriber):** `0x3c44cdddb6a900fa2b585dd299e03d12fa4293bc`
- **Method:** `submit_telemetry_assessment(...)`
- **Arguments:**
  - `policy_id`: `"pol-node-us-east-1"`
  - `incident_telemetry_url`: `"https://logs.example.com/incident-2026-09.json"`
  - `incident_telemetry_hash`: `"b10a8db164e0754105b7a99be72e3fe5ec432ce7d51c7c5c242e4d01a0372332"`

**Expected Verdict & Consensus State Transition [Expected Output]:**
- **Consensus Verdict:** `INDEMNITY_TRIGGERED:LATENCY_BREACH`
- **Status:** `ASSESSING` (Entering 24-hour challenge cooling-off window)
- **Adjudication Rationale:** `"[LATENCY_BREACH] Telemetry conclusively demonstrates P99 latency reached 620ms (guaranteed threshold: 300ms) with error rates within bounds."`
- **Challenge Period Ends At:** `now + 86400`

---

## 2. Technical Architecture & Intelligent Contract Principles

1. **Decentralized Multi-Value Binding & Semantic Consensus**:
   - Rather than checking only a single boolean or surface format, consensus validators independently bind **every value influencing adjudication and payouts**:
     - `is_sla_breached`: Strict boolean decision.
     - `breach_code`: Discrete bounded classification (`NONE`, `LATENCY_BREACH`, `ERROR_RATE_BREACH`, `HEAD_DRIFT_BREACH`, `MULTI_METRIC_BREACH`, `INSUFFICIENT_DATA`).
   - Two validator nodes reaching different substantive metric determinations (e.g. latency vs drift) **will never reach consensus**.

2. **Supreme Appellate Arbitration (Pure Bound Evidence & Dead-Lock Elimination)**:
   - Eliminates dead-lock states when a provider disputes an incident through `adjudicate_sla_dispute`.
   - **Critical Safety Guardrail:** The appellate prompt strictly consumes bound cryptographic evidence (manifest, subscriber telemetry, provider counter-proofs) and **never feeds unverified free-form rationale from prior stages into the payout path**.
   - Appellate validators independently bind both the verdict boolean and `breach_code`, definitively transitioning policies to `BREACH_INDEMNIFIED` or `ACTIVE`.

3. **Zero-Normalization Strict Parsing**:
   - Parses directly via `json.loads` without regex normalizers or markdown stripping.
   - Enforces fail-closed semantics: immediately rejects non-canonical formatting, code fences, or pseudo-JSON outputs.

4. **Deterministic Runtime Context**:
   - Strictly derives time from `gl.message_raw["datetime"]` rather than non-deterministic system clocks (`time.time()`).

5. **Pull-over-Push Safe Settlement Vault & Invariant Ledger**:
   - Conserves pool balance invariants: `Total Inflow = underwritten_pool_balance + claimable_vault`.
   - Beneficiaries withdraw settled funds asynchronously via `claim_vault_credits()`, preventing reentrancy and transfer revert attacks.

6. **Cryptographic Snapshot Anchoring**:
   - Requires 64-character hex SHA-256 digests for benchmark policy terms, telemetry incident logs, and counter-evidence.
   - Consensus validators independently acquire, hash, verify content integrity, and reject tampered evidence.

---

## 3. Public API Specification

- `underwrite_sla_policy(policy_id, subscriber_address, rpc_endpoint_url, benchmark_manifest_url, benchmark_manifest_hash, max_p99_latency_ms, max_error_rate_permille, max_head_drift_blocks, coverage_duration_days)`: Infrastructure provider deposits bond and registers SLA thresholds.
- `submit_telemetry_assessment(policy_id, incident_telemetry_url, incident_telemetry_hash)`: Subscriber submits incident logs triggering GenLayer multi-agent consensus adjudication.
- `dispute_assessment_verdict(policy_id, challenge_rationale)`: 24-hour contestation window for providers before payouts finalize.
- `adjudicate_sla_dispute(policy_id, counter_telemetry_url, counter_telemetry_hash)`: Appellate consensus adjudication resolving disputed policies with counter-evidence without unbound rationale injection.
- `execute_indemnity_payout(policy_id)`: Credits the subscriber via the pull-vault if cooling-off period elapses without dispute.
- `release_matured_underwriting(policy_id)`: Provider reclaims underwriting bond once policy term matures without breach.
- `claim_vault_credits()`: Non-custodial pull withdrawal of settled GEN to recipient address.
- `get_policy_summary(policy_id)`: Returns full JSON summary of an underwriting policy.
- `get_all_policy_ids()`: Returns JSON list of all registered policy identifiers.
- `get_claimable_balance(account_address)`: Returns claimable vault balance for an address.

---

## 4. Reusability Beyond a Demo

SLAOracle serves as a reusable, general-purpose infrastructure primitive for:
1. **Decentralized RPC & Node Infrastructure Networks**: Automated uptime and latency guarantees for Infura/Alchemy-style decentralized alternatives (Pocket, Lava, Ankr).
2. **Decentralized Storage & Cloud Compute (DePIN)**: Verifiable retrieval latency and head-lag insurance for decentralized compute/storage networks (Akash, Filecoin, Render).
3. **Cross-Chain Bridge & Relayer SLA Bonds**: Slashing and insurance mechanisms ensuring relayers meet latency and liveness bounds.

---

## 5. Submission Details

- **Project Title:** `SLAOracle: Autonomous Cloud & RPC SLA Insurance Protocol`
- **Contribution Type:** `Builder Track -> Intelligent Contracts`
- **Primary Track:** `Infrastructure & Cloud Integrity`
- **Submission Notes:**
```plaintext
SLAOracle is an autonomous Cloud & RPC SLA Insurance Protocol built on GenLayer Studionet.

Problem Solved:
Web3 dApps and node operators pay thousands monthly for cloud/RPC services with 99.9% uptime SLAs. However, compensation claims are processed through biased, centralized, and slow manual negotiations.

Technical Architecture:
1. Decentralized Multi-Value Adjudication: Validators independently bind every value influencing payouts (both is_sla_breached boolean and discrete breach_code: LATENCY, ERROR_RATE, HEAD_DRIFT, MULTI_METRIC).
2. Pure Bound Appellate Review: Resolves DISPUTED states by auditing only cryptographic proofs (SHA-256 anchored benchmark, incident logs, counter-telemetry). Completely removes unverified free-form rationale from the payout path.
3. Cryptographic Commitments: Enforces strict SHA-256 anchoring, failing closed on URL drift or tampering.
4. Zero-Normalization Parser: Implements direct json.loads decoding, rejecting markdown fences and pseudo-JSON.
5. Pull-over-Push Safe Settlement: Indemnity claims settle via claimable_vault, eliminating transfer reverts.
```
