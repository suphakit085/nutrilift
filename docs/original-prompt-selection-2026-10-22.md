# Restore the original response prompt

The user selected the contract-off prompt after reviewing the controlled prompt
comparison. Prompt v1.20.1 removes the additional RESPONSE_CONTRACT block from
system-prompt assembly. It retains the base instructions, profile/context blocks,
citation handling, calculator explanations and deterministic goal/safety checks.
This is a scoped prompt change, not a rollback of the presentation-review release.

The comparison's AI scores were exploratory and require human adjudication; this
selection does not establish that the original prompt is universally better.
Known answer-quality issues remain tracked separately. Deployment and live
verification must be recorded separately from preparing or merging this patch.
