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
4. Valid temporary values reach the actual calculator and profile screening.
   They do not write the saved profile. Responses disclose this distinction.
   Explicit target requests render real operands, warnings and scoped sources.
5. General answers receive the typed request constraints; raw extracted quotes
   are never promoted into system instructions. Excluded calculator/menu tools
   are also blocked in application execution, not just by prompt.
6. Output syntax, prohibited dose quantities, unexpected scripts and unsupported
   numeric percentages/intervals are checked before display. One bounded repair
   is permitted; another failure withholds the draft and returns an error.

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
  need a generation call. Cost, quota and first-answer latency must be measured.
- Format checks and matching numbers do not prove that a cited passage entails
  the prose, nor prevent every hallucinated name or conflated research result.
- The original prompt assembly remains; no RESPONSE_CONTRACT framework is added.
  Prompt version is v1.20.3; interpretation schema/policy version is v1.

JSON Schema configuration was checked against the installed SDK and real model.
See [Google's structured output documentation](https://ai.google.dev/gemini-api/docs/generate-content/structured-output).
