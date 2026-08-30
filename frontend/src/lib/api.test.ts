/**
 * Tests for the SSE frame parser.
 *
 * Run with: npm test   (Node's built-in runner, no extra dependencies)
 *
 * This is the one piece of the client a passing `tsc` does not exercise: the
 * backend streams over POST, so EventSource cannot be used and the framing is
 * hand-rolled. The risk is entirely in chunk boundaries - a network chunk can
 * end mid-frame, mid-line, or between the CR and the LF of a line ending.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import { parseSSEFrames } from "./api.ts";

/**
 * A frame in the exact wire format the server produces.
 *
 * sse-starlette writes CRLF. The first version of this parser split on "\n\n"
 * and its tests passed anyway, because they were written against the same
 * wrong assumption as the code. A capture of a live response contained 164
 * occurrences of "\r\n\r\n" and zero of "\n\n" - the chat would have rendered
 * nothing at all. CRLF is the default here; LF is covered explicitly below.
 */
const frame = (event: string, data: unknown) =>
  `event: ${event}\r\ndata: ${JSON.stringify(data)}\r\n\r\n`;

const lfFrame = (event: string, data: unknown) =>
  `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

test("parses a single complete frame", () => {
  const { frames, rest } = parseSSEFrames(frame("delta", { text: "สวัสดี" }));
  assert.equal(frames.length, 1);
  assert.equal(frames[0].event, "delta");
  assert.equal(frames[0].payload.text, "สวัสดี");
  assert.equal(rest, "");
});

test("LF-only framing also works", () => {
  const { frames } = parseSSEFrames(lfFrame("delta", { text: "ก" }));
  assert.equal(frames.length, 1);
  assert.equal(frames[0].payload.text, "ก");
});

test("parses several frames arriving in one chunk", () => {
  const buffer =
    frame("sources", { sources: [{ label: "S1" }] }) +
    frame("delta", { text: "ก" }) +
    frame("delta", { text: "ข" });
  const { frames } = parseSSEFrames(buffer);
  assert.deepEqual(
    frames.map((f) => f.event),
    ["sources", "delta", "delta"],
  );
});

test("holds back an incomplete trailing frame", () => {
  const buffer = frame("delta", { text: "ก" }) + 'event: delta\r\ndata: {"text":"ข"';
  const { frames, rest } = parseSSEFrames(buffer);
  assert.equal(frames.length, 1);
  assert.equal(rest, 'event: delta\ndata: {"text":"ข"');
});

test("a frame split across two chunks is recovered", () => {
  const whole = frame("done", { text: "จบแล้ว", citations: [] });
  const cut = Math.floor(whole.length / 2);

  const first = parseSSEFrames(whole.slice(0, cut));
  assert.equal(first.frames.length, 0, "half a frame must not be emitted");

  const second = parseSSEFrames(first.rest + whole.slice(cut));
  assert.equal(second.frames.length, 1);
  assert.equal(second.frames[0].payload.text, "จบแล้ว");
});

test("a chunk that splits CR from LF is recovered", () => {
  const whole = frame("done", { text: "จบ", citations: [] });
  // Cut between the CR and the LF of the final blank line.
  const cut = whole.length - 1;

  const first = parseSSEFrames(whole.slice(0, cut));
  assert.equal(first.frames.length, 0, "the frame is not terminated yet");

  const second = parseSSEFrames(first.rest + whole.slice(cut));
  assert.equal(second.frames.length, 1);
  assert.equal(second.frames[0].payload.text, "จบ");
  assert.equal(second.rest, "");
});

test("streaming byte-by-byte yields every frame exactly once", () => {
  const stream =
    frame("sources", { sources: [] }) +
    frame("delta", { text: "ควรกิน" }) +
    frame("delta", { text: "โปรตีน" }) +
    frame("tool", { name: "lookup_food" }) +
    frame("done", { text: "ควรกินโปรตีน", citations: [{ label: "S1" }] });

  const seen: string[] = [];
  let buffer = "";
  for (const char of stream) {
    buffer += char;
    const { frames, rest } = parseSSEFrames(buffer);
    for (const f of frames) seen.push(f.event);
    buffer = rest;
  }

  assert.deepEqual(seen, ["sources", "delta", "delta", "tool", "done"]);
  assert.equal(buffer, "", "nothing should be left over");
});

test("reassembles the full answer from delta frames", () => {
  const pieces = ["ควรกิน", "โปรตีน", "วันละ ", "1.6-2.2 g/kg"];
  const buffer = pieces.map((text) => frame("delta", { text })).join("");
  const { frames } = parseSSEFrames(buffer);
  const answer = frames.map((f) => String(f.payload.text)).join("");
  assert.equal(answer, "ควรกินโปรตีนวันละ 1.6-2.2 g/kg");
});

test("keeps the stream alive when one frame has malformed JSON", () => {
  const buffer =
    "event: delta\r\ndata: {not json}\r\n\r\n" + frame("delta", { text: "ต่อได้" });
  const { frames } = parseSSEFrames(buffer);
  assert.equal(frames.length, 1);
  assert.equal(frames[0].payload.text, "ต่อได้");
});

test("ignores frames that carry no data line", () => {
  const { frames } = parseSSEFrames(
    ": keep-alive comment\r\n\r\n" + frame("delta", { text: "x" }),
  );
  assert.equal(frames.length, 1);
});

test("defaults to the message event when none is given", () => {
  const { frames } = parseSSEFrames('data: {"text":"x"}\r\n\r\n');
  assert.equal(frames[0].event, "message");
});

test("tolerates a missing space after the field name", () => {
  const { frames } = parseSSEFrames('event:delta\r\ndata:{"text":"x"}\r\n\r\n');
  assert.equal(frames[0].event, "delta");
  assert.equal(frames[0].payload.text, "x");
});

test("an empty buffer produces nothing", () => {
  const { frames, rest } = parseSSEFrames("");
  assert.equal(frames.length, 0);
  assert.equal(rest, "");
});

test("error frames are surfaced as frames, not dropped", () => {
  const { frames } = parseSSEFrames(frame("error", { message: "เกิดข้อผิดพลาด" }));
  assert.equal(frames[0].event, "error");
  assert.equal(frames[0].payload.message, "เกิดข้อผิดพลาด");
});
