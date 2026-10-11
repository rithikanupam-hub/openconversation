# Translator candidate — 11 October 2026

This publishes the previously untracked Modal runtime and its supporting browser/engine source, including the tested translation-fidelity, reference-selection and reset fixes. It is a review candidate, not a production release or a demonstrated translation-accuracy upgrade. [Comparison and limits](../research/2026-10-11/RESULTS.md).

## Model-free checks

Use Python 3.12 with numpy, soundfile and websockets installed; no speech models, network or GPU are needed:

```sh
python cloud/check_translation_fidelity.py
python cloud/check_reference_quality.py
python cloud/check_voice_lifecycle.py
python cloud/check_replay_session.py
```

## Runtime prerequisites

`modal_app.py` defines the cloud dependencies. Deployment requires a configured Modal account, a `soniox` secret containing `SONIOX_API_KEY`, downloaded model weights in `lingosync-hf-cache`, and an approved cloud budget. No deployment or model-download command is run by these checks.

Use the explicit `LINGOSYNC_APP=lingosync-dev` environment setting for development: the existing default app name is production. The runtime currently enables session recording (`RECORD_SESSIONS=True`); review consent, retention and access before any customer deployment. The published terms file is generic; private test vocabulary is excluded. Voice provenance and unresolved legacy-default provenance are documented in [VOICES.md](VOICES.md).

The frontend sources are included because the Modal websocket/config/warm-up protocol depends on them. This publication reruns syntax and model-free checks; it does not establish browser, multi-user, long-meeting or cloned-voice acceptance. Already-delivered browser audio is not cancelled by the server voice reset. No automatic deployment workflow is included.

`tests/stack_compare/stream_sim.py` is included for the runtime helpers imported by `live.py`; its historical standalone benchmark CLI requires private fixtures that are intentionally not bundled. Use `cloud/replay_session.py` with your own permitted 16 kHz mono WAV for new replays.
