import test from "node:test";
import assert from "node:assert/strict";
import { takeChatAutoScrollRequest } from "../lib/chat-scroll.mjs";

test("요청 turn이 실제 표시된 뒤 자동 스크롤 요청을 한 번만 소비한다", () => {
  const request = { current: "new-turn" };
  assert.equal(takeChatAutoScrollRequest(request, "previous-turn"), false);
  assert.equal(request.current, "new-turn");
  assert.equal(takeChatAutoScrollRequest(request, "new-turn"), true);
  assert.equal(request.current, null);
  assert.equal(takeChatAutoScrollRequest(request, "new-turn"), false);
});
