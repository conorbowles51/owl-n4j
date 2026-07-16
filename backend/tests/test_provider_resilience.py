import unittest
from unittest.mock import patch

import requests

from services.provider_resilience import (
    ProviderUnavailableError,
    get_circuit_breaker,
    guard_provider_call,
    reset_provider_breakers,
)


class ProviderResilienceTests(unittest.TestCase):
    def setUp(self):
        reset_provider_breakers()
        self.addCleanup(reset_provider_breakers)

    def test_retries_transient_failure_then_records_success(self):
        calls = 0

        def flaky():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise requests.exceptions.Timeout("read timed out")
            return "ok"

        with patch.dict("os.environ", {"PROVIDER_RETRY_ATTEMPTS": "2"}):
            result = guard_provider_call("ollama", flaky)

        self.assertEqual(result, "ok")
        self.assertEqual(calls, 2)
        self.assertEqual(get_circuit_breaker("ollama").failure_count, 0)

    def test_opens_circuit_after_repeated_transient_failures(self):
        breaker = get_circuit_breaker("ollama")
        breaker.failure_threshold = 2
        calls = 0

        def timeout():
            nonlocal calls
            calls += 1
            raise requests.exceptions.Timeout("read timed out")

        with patch.dict("os.environ", {"PROVIDER_RETRY_ATTEMPTS": "1"}):
            with self.assertRaises(ProviderUnavailableError):
                guard_provider_call("ollama", timeout)
            with self.assertRaises(ProviderUnavailableError):
                guard_provider_call("ollama", timeout)
            with self.assertRaises(ProviderUnavailableError):
                guard_provider_call("ollama", timeout)

        self.assertEqual(calls, 2)

    def test_non_transient_errors_are_not_retried_or_counted(self):
        calls = 0

        def invalid_request():
            nonlocal calls
            calls += 1
            raise ValueError("LLM returned empty response")

        with self.assertRaises(ValueError):
            guard_provider_call("openai", invalid_request)

        self.assertEqual(calls, 1)
        self.assertEqual(get_circuit_breaker("openai").failure_count, 0)


if __name__ == "__main__":
    unittest.main()
