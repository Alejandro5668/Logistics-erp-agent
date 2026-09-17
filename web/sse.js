// Pure SSE parsing — no DOM, no fetch, no state. Kept separate from app.js
// so the wire-format logic can be reasoned about (and tested) independently
// of how the UI renders each event.

/** Parse one raw "event: X\ndata: Y" block into { type, data }. */
function parseSseEvent(raw) {
  let type = 'message';
  const dataLines = [];
  for (const line of raw.split('\n')) {
    if (line.startsWith('event:')) type = line.slice(6).trim();
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
  }
  let data = {};
  try {
    data = JSON.parse(dataLines.join('\n'));
  } catch (e) {
    /* malformed frame: fall through with empty data rather than throw */
  }
  return { type, data };
}

/**
 * Consume a fetch Response body as an SSE stream, calling `onEvent` for
 * each complete "event/data" frame as it arrives. Buffering (partial
 * frames split across chunks) is handled here so callers never see a
 * half-parsed frame.
 */
async function readSseStream(response, onEvent) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let separatorIndex;
    while ((separatorIndex = buffer.indexOf('\n\n')) >= 0) {
      const raw = buffer.slice(0, separatorIndex);
      buffer = buffer.slice(separatorIndex + 2);
      onEvent(parseSseEvent(raw));
    }
  }
}
