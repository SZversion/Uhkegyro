"""Acceptance coverage for search-completion-stop.md."""
import asyncio
import json

import pytest

from backend.tests.test_parallel_role_search import empty, resolution, search, setup


@pytest.mark.parametrize("roles", [["pose"], ["body", "pose", "view"]])
@pytest.mark.parametrize("has_pins", [False, True])
def test_completion_waits_for_entire_response_without_another_llm_call(
    monkeypatch, snapshot_factory, roles, has_pins
):
    async def run():
        entered, release = asyncio.Event(), asyncio.Event()
        events, enriched = [], []

        async def handler(name, args):
            if name != "search_pinterest_pins":
                assert set(enriched) == set(roles)
                events.append("card")
                return {"term_id": "card"}
            role = args["role"]
            events.append(role)
            if role == roles[-1]:
                entered.set()
                await release.wait()
            if not has_pins:
                return empty(role)
            return {"role": role, "code": None, "pins": [{
                "pin_id": "123", "pin_url": "https://www.pinterest.com/pin/123/",
                "status": "available",
            }]}

        class Widget:
            async def enrich_outcome(self, outcome):
                if outcome.role.value == roles[-1]:
                    release.clear()
                    entered.set()
                    await release.wait()
                enriched.append(outcome.role.value)
                return outcome

        calls = [search(role) for role in roles] + [{
            "id": "card", "name": "get_active_term_card", "arguments": {},
        }]
        worker, adapter = setup(monkeypatch, snapshot_factory, [calls], handler, Widget())
        original = adapter.request_mcp_tool_calls

        async def select(*args, **kwargs):
            assert not adapter.tool_requests, "completed searches must not request another tool selection"
            assert kwargs["required"] is True
            return await original(*args, **kwargs)

        adapter.request_mcp_tool_calls = select
        task = asyncio.create_task(worker._search_outcomes(resolution(roles), request_text="test"))
        try:
            await asyncio.wait_for(entered.wait(), 1)
            assert not task.done() and "card" not in events
            entered.clear()
            release.set()
            await asyncio.wait_for(entered.wait(), 1)
            assert not task.done() and "card" not in events
            release.set()
            outcomes = await asyncio.wait_for(task, 1)
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        assert {role.value for role in outcomes} == set(roles)
        assert events == roles + ["card"]
        assert set(enriched) == set(roles)
        assert all(len(outcome.pins) == int(has_pins) for outcome in outcomes.values())
        if not has_pins:
            assert all(outcome.code.value == "PIN_RESULTS_EMPTY" for outcome in outcomes.values())
        assert len(adapter.tool_requests) == 1
        assert not adapter.decision_requests
        replies = [m for m in adapter.tool_requests[0][0] if m["role"] == "tool"]
        assert [m["tool_call_id"] for m in replies] == [c["id"] for c in calls]
        assert [json.loads(m["content"])["role"] for m in replies[:-1]] == roles
        for _ in range(3):
            await asyncio.wait_for(worker._search_slots.acquire(), 1)
        for _ in range(3):
            worker._search_slots.release()

    asyncio.run(run())
