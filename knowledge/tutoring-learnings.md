# Tutoring Learnings

Distilled 2026-09-17 from princeton-nlp/TutorChat (150), Eedi
Question-Anchored-Tutoring-Dialogues-2k (138 dialogues), knght0wl21
socratic-tutoring-dataset (150), derek-thomas/squad-v1.1-t5-question-generation
(150). 588 docs in the `elearning-tutoring` lane.

## Tutor talk moves (Eedi, 1,190 labeled turns in the 138 indexed dialogues)

The ingest kept 138 of the Eedi dialogues, so these are the label counts that
actually live in `data/index.db` (counted 2026-09-26) — not the source
dataset's full-2k totals:

- `<Press for Accuracy>` (603) — the dominant move: ask the student to be
  precise ("what exactly do you mean by…", "can you say that more precisely").
  Precision-first beats explanation-first.
- `<Keep Together>` (368) — keep the group/session on the same page
  ("let's make sure we're all following"). In 1:1 tutoring this becomes
  "check we're aligned before moving on".
- `<Revoicing>` (186) — restate the student's idea back to them, slightly
  cleaned up ("so you're saying…"). Validates and sharpens their thinking.
- `<Getting Student to Relate>` (16), `<Press for Reasoning>` (15),
  `<Restating>` (2) — rarer, used for deeper conceptual pushes.
- Most turns carry NO labeled move — 1,708 of the 2,898 indexed Eedi tutor
  turns have no label at all (ordinary scaffolding, encouragement, and
  logistics dominate raw turn count). Moves are the deliberate interventions,
  not the filler.

## Socratic discipline

- Never hand over the answer. The socratic corpus structures every case as:
  question → student's incorrect solution → teacher's read of the confusion →
  dialogue that probes the misconception until self-correction.
- Diagnose before responding: the ingest reads the source
  `teacher_described_confusion` column into each digest as the
  `TEACHER READ OF CONFUSION` line — name the misconception to yourself first,
  then pick the question that exposes it.
- Student profiles are short (one line) — adapt tone, not content, to them.

## Dialogue shape (TutorChat, openbook mode)

- Open with the topic and the skills to develop, then let the student drive
  with clarifying questions turn by turn. Tutor turns are explanations (the
  indexed digests clip every tutor turn at 600 chars, so this runbook makes no
  claim about the source answers' full length); student turns are short
  follow-ups.
- Enthusiasm is a signal: follow the student's curiosity, don't force the
  lesson plan order.

## Anchoring (Eedi)

- One question per session. Every dialogue is anchored to a single
  `QuestionId_DQ` with its full text available — the tutor never drifts to
  adjacent topics.
- For an AI study assistant: load the anchor question into context first,
  then tutor only within its scope.

## Question generation (SQuAD pairs)

- Factual quiz questions are generated from a passage's entities and
  relations, not from its opinions. Context (≤900 chars) → questions.
- Training signal for auto-generating quizzes from course content: feed the
  module text, get back who/what/when/why questions with answers in the text.
