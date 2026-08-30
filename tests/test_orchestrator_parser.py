from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from local_service.agent_graph import llm_orchestrator_node, parse_orchestrator_response


class OrchestratorParserTests(unittest.TestCase):
    def test_parses_valid_json(self) -> None:
        parsed = parse_orchestrator_response(
            '{"intent":"chat","route":"answer","confidence":0.8,"needsClarification":false,"clarifyingQuestion":""}'
        )
        self.assertEqual(parsed["intent"], "chat")
        self.assertEqual(parsed["route"], "answer")
        self.assertEqual(parsed["confidence"], 0.8)

    def test_parses_fenced_json(self) -> None:
        parsed = parse_orchestrator_response(
            '```json\n{"intent":"fix","route":"patch","confidence":0.9,"needsClarification":false,"clarifyingQuestion":""}\n```'
        )
        self.assertEqual(parsed["intent"], "fix")
        self.assertEqual(parsed["route"], "patch")

    def test_repairs_missing_comma_between_fields(self) -> None:
        parsed = parse_orchestrator_response(
            '{"intent":"chat" "route":"answer","confidence":0.7,"needsClarification":false,"clarifyingQuestion":""}'
        )
        self.assertEqual(parsed["intent"], "chat")
        self.assertEqual(parsed["route"], "answer")

    def test_repairs_trailing_comma(self) -> None:
        parsed = parse_orchestrator_response(
            '{"intent":"debug","route":"answer","confidence":0.7,"needsClarification":false,"clarifyingQuestion":"",}'
        )
        self.assertEqual(parsed["intent"], "debug")
        self.assertEqual(parsed["route"], "answer")


class OrchestratorFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_malformed_response_keeps_deterministic_route(self) -> None:
        state = {
            "command_text": "explain this",
            "intent": "explain",
            "route": "answer",
            "confidence": 0.2,
            "warnings": [],
        }
        with patch("local_service.agent_graph.ask_ollama", new=AsyncMock(return_value="not json")):
            routed = await llm_orchestrator_node(state)

        self.assertEqual(routed["intent"], "explain")
        self.assertEqual(routed["route"], "answer")
        self.assertFalse(routed["needs_clarification"])
        self.assertTrue(any("parse failed" in warning for warning in routed["warnings"]))
        self.assertFalse(any("skipped" in warning for warning in routed["warnings"]))


if __name__ == "__main__":
    unittest.main()
