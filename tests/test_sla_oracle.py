import pytest
import json
import hashlib
from gltest import *


@pytest.fixture
def contract(direct_deploy, direct_vm):
    direct_vm.warp("2026-09-22T00:00:00Z")
    return direct_deploy("contracts/sla_oracle.py")


def test_initial_state(contract):
    summary = contract.get_policy_summary("non_existent")
    assert summary == "{}"
    all_ids = json.loads(contract.get_all_policy_ids())
    assert all_ids == []
    assert contract.get_claimable_balance("0x1111111111111111111111111111111111111111") == "0"


def test_underwrite_sla_policy_success(contract, direct_vm, direct_alice, direct_bob):
    direct_vm.warp("2026-09-22T00:00:00Z")
    direct_vm.sender = direct_alice
    direct_vm.value = 5000

    policy_id = "pol-node-us-east-1"
    sub_addr = str(direct_bob).lower()
    rpc_url = "https://rpc.mainnet.example.com"
    manifest_url = "https://terms.example.com/sla.json"
    manifest_hash = hashlib.sha256(b"SLA terms: P99 < 300ms, Error < 10 permille").hexdigest().lower()

    contract.underwrite_sla_policy(
        policy_id,
        sub_addr,
        rpc_url,
        manifest_url,
        manifest_hash,
        300,
        10,
        5,
        30
    )

    all_ids = json.loads(contract.get_all_policy_ids())
    assert policy_id in all_ids

    summary_raw = contract.get_policy_summary(policy_id)
    summary = json.loads(summary_raw)
    assert summary["policy_id"] == policy_id
    assert summary["provider"] == str(direct_alice).lower()
    assert summary["subscriber"] == sub_addr
    assert summary["underwriting_bond"] == "5000"
    assert summary["status"] == "ACTIVE"
    assert summary["max_p99_latency_ms"] == "300"
    assert summary["max_error_rate_permille"] == "10"
    assert summary["max_head_drift_blocks"] == "5"


def test_underwrite_sla_policy_duplicate_fails(contract, direct_vm, direct_alice, direct_bob):
    direct_vm.warp("2026-09-22T00:00:00Z")
    direct_vm.sender = direct_alice
    direct_vm.value = 1000

    manifest_hash = hashlib.sha256(b"SLA terms").hexdigest().lower()
    contract.underwrite_sla_policy(
        "pol-dup",
        str(direct_bob).lower(),
        "https://rpc.example.com",
        "https://terms.example.com",
        manifest_hash,
        200,
        5,
        2,
        30
    )

    with pytest.raises(Exception):
        contract.underwrite_sla_policy(
            "pol-dup",
            str(direct_bob).lower(),
            "https://rpc.example.com",
            "https://terms.example.com",
            manifest_hash,
            200,
            5,
            2,
            30
        )


def test_underwrite_sla_policy_zero_value_fails(contract, direct_vm, direct_alice, direct_bob):
    direct_vm.warp("2026-09-22T00:00:00Z")
    direct_vm.sender = direct_alice
    direct_vm.value = 0

    manifest_hash = hashlib.sha256(b"SLA terms").hexdigest().lower()
    with pytest.raises(Exception):
        contract.underwrite_sla_policy(
            "pol-zero",
            str(direct_bob).lower(),
            "https://rpc.example.com",
            "https://terms.example.com",
            manifest_hash,
            200,
            5,
            2,
            30
        )


def test_evidence_integrity_hashes():
    """Verify SHA-256 evidence anchoring logic."""
    manifest_data = "SLA Terms: Guaranteed latency 200ms"
    valid_hash = hashlib.sha256(manifest_data.encode("utf-8")).hexdigest().lower()
    assert len(valid_hash) == 64

    tampered_data = manifest_data + " (modified)"
    tampered_hash = hashlib.sha256(tampered_data.encode("utf-8")).hexdigest().lower()
    assert valid_hash != tampered_hash


def test_strict_json_parsing():
    """Verify zero-normalization JSON parsing rejects markdown fences and pseudo-JSON."""
    fenced_output = "```json\n{\"is_sla_breached\": true, \"reason\": \"Breached P99\"}\n```"
    with pytest.raises(Exception):
        json.loads(fenced_output)

    canonical_output = '{"is_sla_breached": true, "reason": "Breached P99"}'
    parsed = json.loads(canonical_output)
    assert parsed["is_sla_breached"] is True
    assert isinstance(parsed["is_sla_breached"], bool)
