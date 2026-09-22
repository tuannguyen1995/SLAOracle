import unittest
import json
import hashlib

class TestSLAOracleVerification(unittest.TestCase):
    def test_01_strict_json_rejection(self):
        """Bảo đảm parse JSON không qua normalize, chặn đứng code fence."""
        raw_fence = "```json\n{\"is_sla_breached\": true, \"reason\": \"P99 exceeded\"}\n```"
        with self.assertRaises(Exception):
            json.loads(raw_fence)

        canonical = '{"is_sla_breached": true, "reason": "P99 exceeded"}'
        parsed = json.loads(canonical)
        self.assertTrue(parsed["is_sla_breached"])

    def test_02_evidence_sha256_integrity(self):
        """Chứng minh tính bất biến của benchmark terms."""
        terms = "SLA Guaranteed: Max Latency = 200ms"
        expected = hashlib.sha256(terms.encode("utf-8")).hexdigest().lower()
        self.assertEqual(len(expected), 64)

        tampered = terms + " (tampered)"
        self.assertNotEqual(expected, hashlib.sha256(tampered.encode("utf-8")).hexdigest().lower())

if __name__ == "__main__":
    unittest.main()
