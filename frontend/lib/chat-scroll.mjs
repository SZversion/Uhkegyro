export function takeChatAutoScrollRequest(requestRef, latestTurnId) {
  if (!latestTurnId || requestRef.current !== latestTurnId) return false;
  requestRef.current = null;
  return true;
}
