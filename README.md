# SLAOracle: Autonomous Cloud & RPC SLA Insurance Protocol

## Overview
**SLAOracle** is an autonomous Cloud & RPC SLA Insurance Protocol built on GenLayer Studionet.
It provides an automated, non-custodial underwriting pool and real-time incident metric validator for Web3 RPC services and cloud infrastructure.

---

## Technical Architecture & Intelligent Contract Principles

1. **Stateful Telemetry Ledger & Continuous Sampling Matrix**:
   - Rather than static bounty storage, it manages an underwriting bond pool per policy (`underwriting_bond`, `underwritten_pool_balance`).
   - Evaluates multi-metric degradation: **P99 Latency**, **HTTP Error Rate**, and **Block Head Drift**.

2. **Zero-Normalization Strict Parsing**:
   - Parses directly via `json.loads` without regex normalizing hacks.
   - Enforces fail-closed rules: immediately rejects non-canonical formatting, markdown code fences, or pseudo-JSON outputs.

3. **Deterministic Runtime Context**:
   - Strictly derives time from `gl.message_raw["datetime"]` rather than non-deterministic system clocks (`time.time()`).

4. **Pull-over-Push Safe Settlement Vault**:
   - Utilizes `claimable_vault` mapping to credit payouts and bond releases.
   - Beneficiaries withdraw settled funds asynchronously via `claim_vault_credits()`, eliminating external transfer revert attacks.

5. **Cryptographic Snapshot Anchoring**:
   - Requires 64-character hex SHA-256 digests for both benchmark policy terms (`benchmark_manifest_hash`) and telemetry incident logs (`incident_telemetry_hash`).
   - Consensus validators independently acquire, hash, verify content integrity, and reject tampered evidence.

---

## Contract Verification & Lifecycle

- `underwrite_sla_policy`: Provider deposits bond and defines metric boundaries (P99, error permille, head drift).
- `submit_telemetry_assessment`: Subscriber provides verifiable logs; GenLayer multi-agent consensus executes LLM evaluation with live endpoint probing.
- `dispute_assessment_verdict`: 24-hour contestation window for providers before payouts finalize.
- `execute_indemnity_payout`: Credits the subscriber via the pull-vault if cooling-off period elapses without dispute.
- `release_matured_underwriting`: Provider reclaims underwriting bond once policy matures without breach.
- `claim_vault_credits`: Non-custodial pull withdrawal to recipient address.

---

## Submission Details

- **Project Title**: SLAOracle: Autonomous Cloud & RPC SLA Insurance Protocol
- **Contribution Type**: Projects / Intelligent Contracts
- **Primary Track**: Infrastructure & Cloud Integrity
- **Submission Notes**:
```plaintext
SLAOracle is an autonomous Cloud & RPC SLA Insurance Protocol built on GenLayer Studionet.

Problem Solved:
Web3 dApps and node operators pay thousands monthly for cloud/RPC services with 99.9% uptime SLAs. However, compensation claims are processed through biased, centralized, and slow manual negotiations.

Technical Architecture:
1. Decentralized Metric Adjudication: Providers lock native GEN underwriting bonds. When outages occur, clients submit verifiable incident telemetry. Consensus validators query live endpoints and evaluate incident logs against committed SLA terms without centralized oracles.
2. Cryptographic Digest Commitments: Enforces strict SHA-256 hash anchoring for both the SLA benchmark manifest and incident logs, failing closed on mutable URL drift or tampering.
3. Zero-Normalization Parser: Implements direct json.loads decoding, rejecting markdown fences and pseudo-JSON.
4. Pull-over-Push Safe Settlement: Indemnity claims settle via claimable_vault, eliminating transfer reverts.
```
