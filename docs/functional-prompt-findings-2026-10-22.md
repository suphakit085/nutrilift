# Functional prompt findings: runtime remediation

The 24-case functional test found false profile requests for negated calculations,
guessed answers to incomplete pairing questions, unstable medical scope endings,
misattributed personal targets, unsupported percentages, and an extra introduction
in a table-only answer. Repeated outputs represent nine failing cases, not 24
independent defects.

## Changes

- Mask explicitly negated actions for profile routing while preserving a later
  affirmative request. General explanation requests that prohibit calculation do
  not receive the personal-target prompt block.
- Ask for the missing partner in an incomplete pairing question. Fully specified
  pairs and open-ended requests for possible pairings remain answerable.
- Recognize organ/lab-result wording variants and retain the existing medical
  flag across user history. Medical/PED refusals precede retrieval and generation.
- Route explicit personal calculation requests through the existing calculator
  renderer even when the user does not separately request a formula. The same
  current conversation profile, screening decisions, warnings and real operands
  are used. No calculation formula or clinical threshold changes in this patch.
- Explicit user weight/height updates reach the temporary conversation profile
  and calculator, including a corrected value separated from the measurement
  name. Ignore assistant guesses, hypotheticals and negated values; disclose the
  active measurements without changing the saved profile. Explicit reset restores
  saved measurements. Calculator imperatives need not contain a first-person word.
- Keep publication citations separate from actual calculator results in model
  prose, preserving neighboring research clauses and adding calculator provenance.
- Extend the existing source-bound creatine loading FAQ to spelling variants and
  explicit dose exclusions. Without the supporting passage it remains a model
  question. This changes the observed model/rule coverage and must be reported.
- Validate explicit JSON/table/bullet constraints and excluded doses before
  displaying ordinary model prose. Percentage ranges must have numeric support
  in the cited passages. A failed draft gets one bounded repair; another failure
  ends with an error instead of displaying the rejected draft. Repair is recorded
  in the terminal event and may add one generation call.
- Normalize the observed mixed-script spelling of the exercise term "set" and
  known numerical week-unit spellings before validation. Other unexpected scripts
  still trigger repair; normalizing a unit does not authorize an unsupported
  tracking interval. Rejected drafts remain withheld.

The numeric-support check is deliberately limited: matching a number does not
prove semantic entailment, population applicability or clinical correctness.
Human review is still required. Existing verified food/menu tool rendering stays
authoritative. This patch does not reintroduce RESPONSE_CONTRACT; the selected
original prompt assembly remains, with a focused evidence rule and version
v1.20.2 for traceability.

## Validation

Regression cases include paraphrases, negated/affirmative mixed requests, complete
pairing questions, clinical/nonclinical similar words, calculator provenance,
format repair, bounded failure and withholding rejected drafts. The local CI
regression command includes 1,674 tests (76 PostgreSQL/evidence cases deselected;
the CI-excluded food-audit file requires external local evidence). Ruff passed.
Hosted CI separately exercises PostgreSQL and the runtime image.

The real-model retest reuses all 24 frozen input/expected cases and their supplied
contexts, three repetitions each. This is an integration regression with model
and rule routes reported separately, not a prompt-only A/B or a production website
test. Original evidence remains in output/prompt-functional-testing-20261022;
follow-up evidence belongs in output/prompt-functional-fixes-20261022.
