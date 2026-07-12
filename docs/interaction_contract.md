# AttentiveSlides Interaction Contract

## Purpose

The interaction contract separates the main tutoring pipeline from
specific input hardware.

Supported interaction modes:

- `manual`
- `sensor_assisted`
- `hybrid`

Supported target sources:

- `manual_rectangle`
- `manual_aoi`
- `gaze_prediction`
- `whole_slide`

Supported intent sources:

- `typed_text`
- `speech_transcript`
- `ui_action`

Supported confirmation sources:

- `explicit_user_confirmation`
- `manual_correction`
- `automatic_high_confidence`

## Manual privacy mode

Manual mode rejects gaze and speech inputs. A typical interaction uses:

```text
manual rectangle
+ typed command
+ explicit user confirmation
