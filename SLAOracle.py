# v0.2.25
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
from dataclasses import dataclass
import json
import datetime
import hashlib

@gl.evm.contract_interface
class _Recipient:
    class View:
        pass
    class Write:
        pass

class UserError(Exception):
    pass

@allow_storage
@dataclass
class SLAPerformancePolicy:
    policy_id: str
    provider_address: str
    subscriber_address: str
    underwriting_bond: bigint
    status: str             # "ACTIVE", "ASSESSING", "BREACH_INDEMNIFIED", "COMPLIANT_RETAINED", "DISPUTED", "CLOSED"
    rpc_endpoint_url: str
    benchmark_manifest_url: str
    benchmark_manifest_hash: str # SHA-256 của file thỏa thuận benchmark
    incident_telemetry_url: str
    incident_telemetry_hash: str # SHA-256 của chuỗi telemetry lúc xảy ra sự cố
    max_p99_latency_ms: bigint
    max_error_rate_permille: bigint  # 1/1000 (ví dụ 50/1000 = 5%)
    max_head_drift_blocks: bigint
    adjudication_verdict: str        # "INDEMNITY_TRIGGERED", "PERFORMANCE_ACCEPTABLE", "UNRESOLVED"
    adjudication_rationale: str
    metric_confidence: bigint
    created_at_timestamp: bigint
    challenge_period_ends_at: bigint
    last_disputed_timestamp: bigint
    coverage_duration_sec: bigint

class Contract(gl.Contract):
    policies: TreeMap[str, SLAPerformancePolicy]
    policy_catalog: DynArray[str]
    claimable_vault: TreeMap[str, bigint]
    underwritten_pool_balance: bigint
    governor_address: str

    def __init__(self):
        # GenVM automatically initializes TreeMap and DynArray storage fields.
        # DO NOT reassign self.policies = TreeMap() or DynArray() to avoid TypeError/AssertionError.
        self.governor_address = str(gl.message.sender_address).lower()
        self.underwritten_pool_balance = bigint(0)

    def _allocate_credit(self, recipient: str, value: bigint) -> None:
        rec_clean = str(recipient).lower()
        current = self.claimable_vault.get(rec_clean, bigint(0))
        self.claimable_vault[rec_clean] = current + value

    def _get_execution_time(self) -> bigint:
        """Derive trusted deterministic execution timestamp strictly from runtime context."""
        if not hasattr(gl, "message_raw") or not isinstance(gl.message_raw, dict):
            raise UserError("Execution environment missing transaction message context")
        raw_datetime = gl.message_raw.get("datetime", None)
        if not raw_datetime:
            raise UserError("Transaction context missing deterministic 'datetime'")
        try:
            iso_str = str(raw_datetime)
            if iso_str.endswith("Z"):
                iso_str = iso_str[:-1] + "+00:00"
            parsed_epoch = int(datetime.datetime.fromisoformat(iso_str).timestamp())
            if parsed_epoch <= 0:
                raise UserError("Deterministic clock resolved non-positive timestamp")
            return bigint(parsed_epoch)
        except Exception as err:
            raise UserError(f"Failed to decode deterministic timestamp: {str(err)}")

    def _parse_llm_json(self, raw_input) -> dict:
        """
        ZERO-NORMALIZATION STRICT JSON PARSER:
        Direct json.loads only. Rejects code fences, markdown, or pseudo-JSON immediately.
        """
        if isinstance(raw_input, dict):
            parsed_dict = raw_input
        else:
            try:
                parsed_dict = json.loads(str(raw_input).strip())
            except Exception as e:
                return {
                    "is_sla_breached": False,
                    "reason": f"FAIL-CLOSED: Response failed strict JSON decoding: {str(e)}"
                }

        if not isinstance(parsed_dict, dict):
            return {"is_sla_breached": False, "reason": "FAIL-CLOSED: Output root is not an object."}

        if "is_sla_breached" not in parsed_dict or "reason" not in parsed_dict:
            return {"is_sla_breached": False, "reason": "FAIL-CLOSED: Missing required fields."}

        is_breached = parsed_dict["is_sla_breached"]
        rationale = parsed_dict["reason"]

        if type(is_breached) is not bool:
            return {"is_sla_breached": False, "reason": "FAIL-CLOSED: 'is_sla_breached' must be a strict boolean."}

        if not isinstance(rationale, str) or len(rationale.strip()) == 0:
            return {"is_sla_breached": False, "reason": "FAIL-CLOSED: 'reason' must be non-empty text."}

        return {"is_sla_breached": is_breached, "reason": rationale.strip()}

    @gl.public.write.payable
    def underwrite_sla_policy(
        self,
        policy_id: str,
        subscriber_address: str,
        rpc_endpoint_url: str,
        benchmark_manifest_url: str,
        benchmark_manifest_hash: str,
        max_p99_latency_ms: int,
        max_error_rate_permille: int,
        max_head_drift_blocks: int,
        coverage_duration_days: int = 30
    ) -> None:
        """Infrastructure provider deposits an SLA bond into custody for a specific subscriber."""
        if policy_id in self.policies:
            raise UserError(f"Policy ID '{policy_id}' already registered")

        locked_bond = gl.message.value
        if locked_bond <= bigint(0):
            raise UserError("Underwriting bond must be greater than zero")

        clean_rpc = rpc_endpoint_url.strip()
        if not clean_rpc.startswith("http://") and not clean_rpc.startswith("https://"):
            raise UserError("Valid HTTP/HTTPS RPC endpoint URL required")

        clean_manifest_url = benchmark_manifest_url.strip()
        if not clean_manifest_url.startswith("http://") and not clean_manifest_url.startswith("https://") and not clean_manifest_url.startswith("ipfs://"):
            raise UserError("Valid benchmark manifest URL required")

        clean_manifest_hash = benchmark_manifest_hash.strip().lower()
        if len(clean_manifest_hash) != 64 or not all(c in "0123456789abcdef" for c in clean_manifest_hash):
            raise UserError("Evidence commitment failed: benchmark_manifest_hash must be a 64-char hex SHA-256 digest")

        caller = str(gl.message.sender_address).lower()
        now = self._get_execution_time()
        coverage_seconds = bigint(coverage_duration_days if coverage_duration_days > 0 else 30) * bigint(86400)

        self.policy_catalog.append(policy_id)
        self.underwritten_pool_balance += locked_bond

        self.policies[policy_id] = SLAPerformancePolicy(
            policy_id=policy_id,
            provider_address=caller,
            subscriber_address=subscriber_address.strip().lower(),
            underwriting_bond=locked_bond,
            status="ACTIVE",
            rpc_endpoint_url=clean_rpc,
            benchmark_manifest_url=clean_manifest_url,
            benchmark_manifest_hash=clean_manifest_hash,
            incident_telemetry_url="",
            incident_telemetry_hash="",
            max_p99_latency_ms=bigint(max_p99_latency_ms),
            max_error_rate_permille=bigint(max_error_rate_permille),
            max_head_drift_blocks=bigint(max_head_drift_blocks),
            adjudication_verdict="NONE",
            adjudication_rationale="Policy underwritten and active; monitoring service metrics",
            metric_confidence=bigint(0),
            created_at_timestamp=now,
            challenge_period_ends_at=bigint(0),
            last_disputed_timestamp=bigint(0),
            coverage_duration_sec=coverage_seconds
        )

    @gl.public.write
    def submit_telemetry_assessment(
        self,
        policy_id: str,
        incident_telemetry_url: str,
        incident_telemetry_hash: str
    ) -> None:
        """Subscriber submits performance logs when degradation or downtime occurs."""
        if policy_id not in self.policies:
            raise UserError("Policy identifier not found")
        policy = self.policies[policy_id]

        if policy.status != "ACTIVE":
            raise UserError(f"Policy not eligible for incident claim (Current status: {policy.status})")

        caller = str(gl.message.sender_address).lower()
        if caller != policy.subscriber_address:
            raise UserError("Only the registered subscriber can file an SLA claim")

        clean_telem_url = incident_telemetry_url.strip()
        if not clean_telem_url.startswith("http://") and not clean_telem_url.startswith("https://") and not clean_telem_url.startswith("ipfs://"):
            raise UserError("Valid telemetry URL required")

        clean_telem_hash = incident_telemetry_hash.strip().lower()
        if len(clean_telem_hash) != 64 or not all(c in "0123456789abcdef" for c in clean_telem_hash):
            raise UserError("Evidence commitment failed: incident_telemetry_hash must be a 64-char hex SHA-256 digest")

        policy.incident_telemetry_url = clean_telem_url
        policy.incident_telemetry_hash = clean_telem_hash

        rpc_url = policy.rpc_endpoint_url
        manifest_url = policy.benchmark_manifest_url
        manifest_hash = policy.benchmark_manifest_hash
        p99_limit = str(policy.max_p99_latency_ms)
        err_limit = str(policy.max_error_rate_permille)
        drift_limit = str(policy.max_head_drift_blocks)

        def leader_fn():
            # 1. Acquire & Verify Benchmark Manifest Digest
            try:
                manifest_res = gl.nondet.web.render(manifest_url, mode="text")
                manifest_content = str(manifest_res)
                computed_man_hash = hashlib.sha256(manifest_content.encode("utf-8")).hexdigest().lower()
                if computed_man_hash != manifest_hash:
                    return {
                        "is_sla_breached": False,
                        "reason": f"EVIDENCE INTEGRITY MISMATCH: Manifest hash mismatch! Expected {manifest_hash}, computed {computed_man_hash}"
                    }
            except Exception as e:
                return {"is_sla_breached": False, "reason": f"Failed to acquire benchmark terms: {str(e)}"}

            # 2. Acquire & Verify Telemetry Incident Digest
            try:
                telem_res = gl.nondet.web.render(clean_telem_url, mode="text")
                telem_content = str(telem_res)
                computed_telem_hash = hashlib.sha256(telem_content.encode("utf-8")).hexdigest().lower()
                if computed_telem_hash != clean_telem_hash:
                    return {
                        "is_sla_breached": False,
                        "reason": f"EVIDENCE INTEGRITY MISMATCH: Telemetry hash mismatch! Expected {clean_telem_hash}, computed {computed_telem_hash}"
                    }
            except Exception as e:
                return {"is_sla_breached": False, "reason": f"Failed to acquire telemetry logs: {str(e)}"}

            # 3. Live Endpoint Status Probe
            live_probe_status = "HEALTHY"
            try:
                probe_res = gl.nondet.web.render(rpc_url, mode="text")
                probe_str = str(probe_res)
                if any(err_code in probe_str[:400].lower() for err_code in ["502 bad gateway", "503 service unavailable", "504 gateway timeout", "rate limit exceeded"]):
                    live_probe_status = "DEGRADED"
            except Exception:
                live_probe_status = "UNREACHABLE"

            # 4. Multi-Agent Performance Evaluation Prompt
            prompt = f"""You are the Autonomous Cloud SLA & RPC Infrastructure Oracle on GenLayer.
Evaluate the telemetry data against the guaranteed performance thresholds.

SERVICE ENDPOINT:
{rpc_url} (Current Live Probe State: {live_probe_status})

GUARANTEED THRESHOLDS:
- Max P99 Latency: {p99_limit} ms
- Max Error Rate: {err_limit} per mille (1/1000)
- Max Block Head Drift: {drift_limit} blocks

BENCHMARK SPECIFICATION:
{manifest_content}

UNTRUNCATED INCIDENT TELEMETRY:
{telem_content}

RULES FOR DECISION:
1. Return is_sla_breached: true ONLY if the telemetry conclusively proves latency exceeded {p99_limit} ms, error rate exceeded {err_limit}/1000, or head drift exceeded {drift_limit} blocks.
2. If metrics were within bounds, or the logs are fabricated/inconclusive, return is_sla_breached: false.

Return STRICT JSON only:
{{"is_sla_breached": true, "reason": "Detailed metric breach justification"}}
OR
{{"is_sla_breached": false, "reason": "Detailed justification confirming acceptable performance"}}"""

            try:
                exec_res = gl.nondet.exec_prompt(prompt, response_format="json")
                return self._parse_llm_json(exec_res)
            except Exception as e:
                return {"is_sla_breached": False, "reason": f"LLM execution fault: {str(e)}"}

        def validator_fn(leader_res) -> bool:
            if not isinstance(leader_res, gl.vm.Return):
                return False
            l_data = self._parse_llm_json(leader_res.calldata if hasattr(leader_res, "calldata") else leader_res)
            if not isinstance(l_data, dict) or type(l_data.get("is_sla_breached")) is not bool:
                return False

            mine_data = leader_fn()
            if not isinstance(mine_data, dict) or type(mine_data.get("is_sla_breached")) is not bool:
                return False

            return l_data["is_sla_breached"] == mine_data["is_sla_breached"]

        consensus_output = gl.vm.run_nondet(leader_fn, validator_fn)
        final_assessment = self._parse_llm_json(consensus_output)

        is_breached = final_assessment.get("is_sla_breached", False)
        rationale = str(final_assessment.get("reason", "Consensus concluded.")).strip()

        now = self._get_execution_time()
        policy.adjudication_rationale = rationale

        if is_breached:
            policy.adjudication_verdict = "INDEMNITY_TRIGGERED"
            policy.challenge_period_ends_at = now + bigint(86400) # 24h cooling-off challenge period
            policy.status = "ASSESSING"
        else:
            policy.adjudication_verdict = "PERFORMANCE_ACCEPTABLE"
            policy.status = "ACTIVE"

        self.policies[policy_id] = policy

    @gl.public.write
    def dispute_assessment_verdict(self, policy_id: str, challenge_rationale: str) -> None:
        """Provider challenges an indemnification verdict within the 24-hour cooling-off window."""
        if policy_id not in self.policies:
            raise UserError("Policy not found")
        policy = self.policies[policy_id]

        if policy.status != "ASSESSING":
            raise UserError("Policy is not in a contestable assessment stage")

        caller = str(gl.message.sender_address).lower()
        if caller != policy.provider_address:
            raise UserError("Only the underwriter provider can contest this assessment")

        now = self._get_execution_time()
        if now >= policy.challenge_period_ends_at:
            raise UserError("The 24-hour contestation window has expired")

        policy.status = "DISPUTED"
        policy.last_disputed_timestamp = now
        policy.adjudication_rationale = f"[CONTESTED BY PROVIDER] {challenge_rationale.strip()} | Prior: {policy.adjudication_rationale}"
        self.policies[policy_id] = policy

    @gl.public.write
    def adjudicate_sla_dispute(self, policy_id: str, counter_telemetry_url: str, counter_telemetry_hash: str) -> None:
        """
        Supreme Appellate Review: Resolves DISPUTED policies definitively.
        Validators re-audit the benchmark manifest, subscriber telemetry, and provider counter-evidence.
        Transitions state to either BREACH_INDEMNIFIED (Subscriber compensated) or ACTIVE (Provider exonerated).
        """
        if policy_id not in self.policies:
            raise UserError("Policy not found")
        policy = self.policies[policy_id]

        if policy.status != "DISPUTED":
            raise UserError("Policy is not in DISPUTED status")

        caller = str(gl.message.sender_address).lower()
        if caller != policy.provider_address and caller != policy.subscriber_address:
            raise UserError("Only policy participants can trigger appellate adjudication")

        clean_counter_url = counter_telemetry_url.strip()
        if not clean_counter_url.startswith("http://") and not clean_counter_url.startswith("https://") and not clean_counter_url.startswith("ipfs://"):
            raise UserError("Valid counter telemetry URL required")

        clean_counter_hash = counter_telemetry_hash.strip().lower()
        if len(clean_counter_hash) != 64 or not all(c in "0123456789abcdef" for c in clean_counter_hash):
            raise UserError("Evidence commitment failed: counter_telemetry_hash must be a 64-char hex SHA-256 digest")

        manifest_url = policy.benchmark_manifest_url
        manifest_hash = policy.benchmark_manifest_hash
        orig_telem_url = policy.incident_telemetry_url
        orig_telem_hash = policy.incident_telemetry_hash
        p99_limit = str(policy.max_p99_latency_ms)
        err_limit = str(policy.max_error_rate_permille)
        drift_limit = str(policy.max_head_drift_blocks)
        dispute_context = policy.adjudication_rationale

        def appeal_leader_fn():
            # Verify counter-telemetry digest
            try:
                c_res = gl.nondet.web.render(clean_counter_url, mode="text")
                c_text = str(c_res)
                computed_c_hash = hashlib.sha256(c_text.encode("utf-8")).hexdigest().lower()
                if computed_c_hash != clean_counter_hash:
                    return {
                        "is_sla_breached": True,
                        "reason": f"APPELLATE FAILURE: Counter-evidence hash mismatch! Expected {clean_counter_hash}, got {computed_c_hash}"
                    }
            except Exception as e:
                return {"is_sla_breached": True, "reason": f"Failed to acquire counter-evidence: {str(e)}"}

            # Retrieve original evidence
            try:
                m_res = gl.nondet.web.render(manifest_url, mode="text")
                m_text = str(m_res)
                t_res = gl.nondet.web.render(orig_telem_url, mode="text")
                t_text = str(t_res)
            except Exception as e:
                return {"is_sla_breached": True, "reason": f"Failed to acquire original audit logs: {str(e)}"}

            prompt = f"""You are the Appellate Chief Justice of the GenLayer Infrastructure & SLA Court.
Re-audit the contested SLA incident using the provider's counter-evidence against original claims.

THRESHOLDS: Max P99 Latency = {p99_limit}ms, Max Error Rate = {err_limit}/1000, Max Drift = {drift_limit} blocks

BENCHMARK SPECIFICATION:
{m_text}

SUBSCRIBER INCIDENT LOGS:
{t_text}

DISPUTE CONTEXT & OBJECTION:
{dispute_context}

PROVIDER COUNTER-TELEMETRY & PROOFS:
{c_text}

DECISION MANDATE:
1. Return is_sla_breached: false IF the provider proves metrics were within acceptable limits or the incident was client-side/unrelated.
2. Return is_sla_breached: true IF the SLA breach is upheld despite counter-evidence.

Return STRICT JSON only:
{{"is_sla_breached": true|false, "reason": "Thorough appellate adjudication rationale"}}"""

            try:
                res = gl.nondet.exec_prompt(prompt, response_format="json")
                return self._parse_llm_json(res)
            except Exception as e:
                return {"is_sla_breached": True, "reason": f"Appellate LLM error: {str(e)}"}

        def appeal_validator_fn(leader_res) -> bool:
            if not isinstance(leader_res, gl.vm.Return):
                return False
            l_data = self._parse_llm_json(leader_res.calldata if hasattr(leader_res, "calldata") else leader_res)
            if not isinstance(l_data, dict) or type(l_data.get("is_sla_breached")) is not bool:
                return False
            mine_data = appeal_leader_fn()
            if not isinstance(mine_data, dict) or type(mine_data.get("is_sla_breached")) is not bool:
                return False
            return l_data["is_sla_breached"] == mine_data["is_sla_breached"]

        res = gl.vm.run_nondet(appeal_leader_fn, appeal_validator_fn)
        final_verdict = self._parse_llm_json(res)

        is_breached = final_verdict.get("is_sla_breached", True)
        rationale = str(final_verdict.get("reason", "Appellate review finalized.")).strip()

        policy.adjudication_rationale = f"[APPELLATE DECREE] {rationale} | Prior: {dispute_context}"

        if is_breached:
            # Breach upheld: Indemnify subscriber immediately
            bond_val = policy.underwriting_bond
            policy.underwriting_bond = bigint(0)
            policy.status = "BREACH_INDEMNIFIED"
            self.underwritten_pool_balance -= bond_val
            self._allocate_credit(policy.subscriber_address, bond_val)
        else:
            # Provider exonerated: Policy returns to active state
            policy.status = "ACTIVE"
            policy.adjudication_verdict = "PERFORMANCE_ACCEPTABLE"

        self.policies[policy_id] = policy

    @gl.public.write
    def execute_indemnity_payout(self, policy_id: str) -> None:
        """Finalizes compensation to the subscriber strictly after cooling-off period elapses."""
        if policy_id not in self.policies:
            raise UserError("Policy not found")
        policy = self.policies[policy_id]

        if policy.status != "ASSESSING":
            raise UserError("Policy is not awaiting payout settlement")

        caller = str(gl.message.sender_address).lower()
        if caller != policy.subscriber_address and caller != policy.provider_address:
            raise UserError("Unauthorized settlement executor")

        now = self._get_execution_time()
        if now < policy.challenge_period_ends_at:
            raise UserError("24-hour cooling-off period has not elapsed yet")

        bond_amount = policy.underwriting_bond
        policy.underwriting_bond = bigint(0)
        policy.status = "BREACH_INDEMNIFIED"
        self.underwritten_pool_balance -= bond_amount

        # Safe Pull-over-Push credit
        self._allocate_credit(policy.subscriber_address, bond_amount)
        self.policies[policy_id] = policy

    @gl.public.write
    def release_matured_underwriting(self, policy_id: str) -> None:
        """Provider reclaims bond after policy duration expires with no breach claims."""
        if policy_id not in self.policies:
            raise UserError("Policy not found")
        policy = self.policies[policy_id]

        if policy.status != "ACTIVE":
            raise UserError(f"Cannot reclaim bond while policy is in status '{policy.status}'")

        caller = str(gl.message.sender_address).lower()
        if caller != policy.provider_address:
            raise UserError("Only the underwriting provider can release matured funds")

        now = self._get_execution_time()
        if now < policy.created_at_timestamp + policy.coverage_duration_sec:
            raise UserError("Policy coverage term has not reached maturity")

        bond_amount = policy.underwriting_bond
        policy.underwriting_bond = bigint(0)
        policy.status = "CLOSED"
        self.underwritten_pool_balance -= bond_amount

        self._allocate_credit(policy.provider_address, bond_amount)
        self.policies[policy_id] = policy

    @gl.public.write
    def claim_vault_credits(self) -> None:
        """Non-custodial Pull settlement: Beneficiaries withdraw settled GEN safely."""
        caller = str(gl.message.sender_address).lower()
        balance = self.claimable_vault.get(caller, bigint(0))
        if balance <= bigint(0):
            raise UserError("No claimable credits available in vault")

        self.claimable_vault[caller] = bigint(0)
        _Recipient(Address(caller)).emit_transfer(value=u256(int(balance)))

    @gl.public.view
    def get_policy_summary(self, policy_id: str) -> str:
        if policy_id not in self.policies:
            return "{}"
        p = self.policies[policy_id]
        return json.dumps({
            "policy_id": p.policy_id,
            "provider": p.provider_address,
            "subscriber": p.subscriber_address,
            "underwriting_bond": str(p.underwriting_bond),
            "status": p.status,
            "rpc_endpoint_url": p.rpc_endpoint_url,
            "benchmark_manifest_url": p.benchmark_manifest_url,
            "benchmark_manifest_hash": p.benchmark_manifest_hash,
            "incident_telemetry_url": p.incident_telemetry_url,
            "incident_telemetry_hash": p.incident_telemetry_hash,
            "max_p99_latency_ms": str(p.max_p99_latency_ms),
            "max_error_rate_permille": str(p.max_error_rate_permille),
            "max_head_drift_blocks": str(p.max_head_drift_blocks),
            "verdict": p.adjudication_verdict,
            "rationale": p.adjudication_rationale,
            "created_at": str(p.created_at_timestamp),
            "challenge_ends_at": str(p.challenge_period_ends_at),
            "last_disputed_at": str(p.last_disputed_timestamp)
        })

    @gl.public.view
    def get_all_policy_ids(self) -> str:
        catalog = []
        for pid in self.policy_catalog:
            catalog.append(pid)
        return json.dumps(catalog)

    @gl.public.view
    def get_claimable_balance(self, account_address: str) -> str:
        return str(self.claimable_vault.get(str(account_address).lower(), bigint(0)))
