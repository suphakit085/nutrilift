# Functional prompt findings: semantic request interpretation

The original 24 functional cases, repeated three times, exposed nine failing
cases. Plausible prose could conceal stale calculator inputs. Intermediate
wording-specific fixes are preserved in evaluation artifacts but superseded:
the final production path does not infer new request semantics by expanding
regular expressions one phrase at a time.

## Production flow

1. Existing deterministic safety checks can refuse before any model call.
2. `stream_understood_chat` asks the current model for a JSON request state,
   using an explicit JSON Schema. The schema separates the requested operation,
   excluded actions, personal context, medical concern, missing information,
   output format, and temporary measurements/goal.
3. Pydantic validates types/enums and rejects extra fields. Measurement/goal
   changes require exact quotes from numbered user turns; assistant guesses
   cannot be quoted as user evidence. Numeric syntax is checked independently.
   Contradictory or ungrounded state stops execution and asks for clarification.
   Control fields are mandatory: exclusions cannot disappear through omitted
   defaults. Empty/truncated generations are service failures, not missing user
   information; the same input gets at most one transient-only retry.
   Network/read timeouts also return a service error without another long wait;
   they do not ask the user to correct their data. A bare429 does not establish
   whether the limit is per-minute or daily, so the UI does not claim a period.
4. Valid temporary values reach the actual calculator and profile screening.
   They do not write the saved profile. Responses disclose this distinction.
   Explicit target requests render real operands, warnings and scoped sources.
5. General answers receive the typed request constraints; raw extracted quotes
   are never promoted into system instructions. Excluded calculator/menu tools
   are also blocked in application execution, not just by prompt.
   An explicitly no-dose loading question can use a supported creatine fact
   selected by typed topic, provided the canonical passage is retrieved. This
   program-rendered response is not counted as a generated-model answer.
6. Output syntax, prohibited dose quantities, unexpected scripts and unsupported
   numeric percentages/intervals are checked before display. Semantic review is
   an evidence ledger, not a model verdict: the program splits the draft into
   units at citation-label boundaries (JSON string leaves or lines otherwise)
   and the sources into numbered paragraphs (`S2.3`). The model classifies each
   unit (research, general fact, advice, evidence gap, personal value, framing),
   marks attributions to studies/evidence, and lists the paragraph ids that
   state it. The program then rejects a label whose own paragraphs do not
   support the unit, an evidence claim with support but no label, and an
   evidence claim no paragraph states. Other defects (invented user facts,
   excluded actions, format) refer to unit ids, so fragments are exact by
   construction. The ledger is returned with the answer for audit. One bounded
   repair is permitted; another failure withholds the draft and returns an
   error. Provider faults or an incomplete ledger get one retry of the same draft.

The interpreter lists the user's exclusion phrases before deriving
`blocked_actions`. Every interpreter quote that the model emitted as JSON
Unicode escapes was corrupted (4/4 in recorded runs) while every literal Thai
quote was exact (19/19); a prompt instruction alone did not stop the escapes.
An invalid or ungrounded interpretation therefore receives one correction
naming the exact validation error. The checks are unchanged, so a second
ungrounded answer still stops.

The API and main evaluation runner use the semantic entry point. `stream_chat`
and `collect_answer` remain low-level executor interfaces for existing unit
tests; they are not evidence that language interpretation has been tested.
Full-system evaluations must use `stream_understood_chat` or
`collect_understood_answer`.

## Boundaries and tradeoffs

- The semantic model is fallible. Quote presence proves provenance, not complete
  semantic correctness. Repetition/paraphrase tests remain necessary.
- The model may add a medical concern but cannot clear an existing safety flag.
  Calculator formulas, nutrition scope and specialist thresholds are unchanged.
- Existing legacy safety/menu/food handlers still contain established text
  rules. This change replaces the new phrase-by-phrase intent/measurement fixes;
  it does not claim that all regular expressions have been removed from the app.
- Regex remains appropriate for syntax checks such as numbers, citations and
  Markdown. It is not the new mechanism for interpreting negation/corrections.
- Interpretation adds one provider call on a turn that is not refused early;
  target/menu answers then use application calculation, while knowledge answers
  need generation and semantic review calls. Repair can add another generation
  and review pair. Cost, quota and first-answer latency must be measured.
- Format checks and matching numbers do not prove citation entailment. The
  ledger forces a pointer for every accepted citation, but choosing a paragraph
  that does not actually state the claim is still a model judgement. Confirmed
  misses: unlabelled whey claims classified as "general fact" in a creatine
  context (PT20), and "whey can be taken with milk" asserted from silent
  sources (VX03). A side-by-side entailment pass caught both in replay but also
  rejected 6/19 previously accepted drafts, so it was not adopted here.
- Interpretation can still choose a wrong task: one of three VX03 runs asked
  for a missing pairing item although both items were given.
- The original prompt assembly remains; no RESPONSE_CONTRACT framework is added.
  Prompt version is v1.20.3; interpretation schema/policy version is v3.

JSON Schema configuration was checked against the installed SDK and real model.
See [Google's structured output documentation](https://ai.google.dev/gemini-api/docs/generate-content/structured-output).
