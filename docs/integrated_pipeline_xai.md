# Integrated Pipeline-Level XAI

## Purpose

The integrated XAI view explains the complete observable
Human-AI interaction pipeline through four questions:

1. Why this target?
2. Why this intent?
3. Why this answer?
4. How reliable is the pipeline?

## Target explanation

The target section reports:

- manual rectangle or whole-slide source;
- normalized rectangle;
- AOI overlap candidates;
- proposed AOI;
- confirmed AOI;
- learner correction;
- correction provenance.

It explains geometric mapping and explicit user control. It does not
claim that an observable signal reveals a private mental state.

## Intent explanation

The intent section reports:

- typed-text or UI-action source;
- original command;
- resolved intent;
- parser confidence;
- deictic-reference detection;
- explicit target hint;
- whether the learner explicitly selected a Quick action.

## Answer explanation

The answer section reports:

- response mode;
- public decision summary;
- educational claims;
- source IDs;
- source previews;
- whether each cited source is valid;
- external-knowledge and uncertainty indicators.

## Reliability

Reliability is categorical rather than an arbitrary numerical score:

- `pending`: insufficient evidence is available;
- `supported`: confirmation and grounding validation passed;
- `caution`: the answer is available but warnings exist;
- `unsupported`: grounding validation failed.

Possible warnings include:

- incomplete citation coverage;
- confirmed AOI not cited;
- fallback response;
- provider retry;
- explicit uncertainty;
- disabled cloud permission.

## Corrective control

The learner is given concrete actions such as:

- adjust the rectangle;
- rewrite the command;
- correct the AOI;
- confirm the interaction;
- inspect unsupported claims;
- regenerate the answer.

## Safety and privacy

The public payload excludes:

- hidden Chain-of-Thought;
- raw provider responses;
- prompt messages;
- provider request IDs;
- API credentials.

Camera and microphone remain disabled in Manual mode.
