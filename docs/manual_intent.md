# Manual Typed Intent

## Input methods

The Main UI supports two intent sources:

- `typed_text`
- `ui_action`

Both are converted into the Stage 1 `IntentInput` contract.

## Quick actions

The current quick actions are:

- Explain
- Summarize
- Simplify
- Step by step
- Compare
- Quiz

A quick action is treated as an explicit learner choice and therefore
uses intent confidence `1.0`.

Typed text continues to use the existing rule-based intent parser.

## Explainability

The interface exposes:

- original command;
- intent source;
- resolved intent;
- intent confidence;
- deictic-reference detection;
- explicit target hint;
- whether the intent was inferred or explicitly selected.

## Current limitations

- confirmation is not active;
- compare currently warns when only one target is available;
- TutorAgent is not called;
- cloud LLM is not called.
