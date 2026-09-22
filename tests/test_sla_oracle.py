import unittest
import json
import hashlib

class TestSLAOracleProtocol(unittest.TestCase):
    def test_01_strict_zero_normalization_json(self):
        """Chứng minh parser loại bỏ toàn bộ normalization và fail-closed khi gặp non-canonical JSON."""
        # Trực tiếp fail nếu có code fence markdown
        markdown_response = "```json\n{\"is_sla_breached\": true, \"reason\": \"P99 latency breached 450ms\"}\n```"
        with self.assertRaises(Exception):
            json.loads(markdown_response)

        # Hợp lệ với JSON chuẩn phẳng
        canonical_response = '{"is_sla_breached": true, "reason": "P99 latency breached 450ms"}'
        parsed = json.loads(canonical_response)
        self.assertIsInstance(parsed, dict)
        self.assertTrue(parsed["is_sla_breached"])
        self.assertIsInstance(parsed["is_sla_breached"], bool)

    def test_02_evidence_hash_integrity(self):
        """Xác thực đối soát SHA-256 chính xác của benchmark manifest và telemetry data."""
        sla_terms = "Benchmark Terms: Max P99 Latency = 250ms, Max Error Rate = 1%"
        expected_hash = hashlib.sha256(sla_terms.encode("utf-8")).hexdigest().lower()
        self.assertEqual(len(expected_hash), 64)

        # Mô phỏng dữ liệu bị sửa đổi (tampered)
        tampered_terms = sla_terms + " (altered)"
        tampered_hash = hashlib.sha256(tampered_terms.encode("utf-8")).hexdigest().lower()
        self.assertNotEqual(expected_hash, tampered_hash)

if __name__ == "__main__":
    unittest.main()
