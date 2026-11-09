# A5: Transcribe speech-to-text

**Switch:** `STT_PROVIDER=transcribe` (existing setting, new value). Needs `AWS_REGION`, `S3_BUCKET`.

**Goal:** voice commands use Amazon Transcribe behind `SpeechService`.

**Files**
- New `services/language/app/speech_transcribe.py`: `TranscribeSpeech`.
- Edit `app/speech.py` (`build_speech`) and `app/config.py`.
- **Contract change (P8, additive):** add `"transcribe"` to `TranscribeResult.provider`, then regenerate the JSON Schema and TS types. Reporting `whisper` here would be false.

**Requirements**
- Reuse `decode_audio` first, so the 60-second limit and bad-audio errors stay identical. Upload the decoded samples as 16 kHz mono 16-bit WAV to `tmp/speech/<uuid>.wav`, so the format is always known.
- Start a uniquely named job, poll about once a second up to a deadline, read the transcript from `TranscriptFileUri`, and always delete the S3 object and the job.
- Only languages in an explicit map are accepted (`en` → `en-IN`). Anything else is a 422 `VALIDATION_ERROR`, matching Whisper.
- Botocore errors, `FAILED` jobs, HTTP errors and timeouts become `ServiceError(503, UPSTREAM_UNAVAILABLE, "Speech service is unavailable.")`.
- Trim the transcript to `MAX_TRANSCRIPT_CHARS`. `status` is `"configured"`.

**Tests (fakes):** success returns text and `provider="transcribe"`, cleanup runs on success and failure, failed job and timeout → 503, unknown language → 422, bad audio → 415 with nothing uploaded.

**Known trade-off:** batch jobs take seconds. `STT_PROVIDER=whisper` stays available.
