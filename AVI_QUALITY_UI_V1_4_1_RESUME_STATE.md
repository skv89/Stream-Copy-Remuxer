# Stream Copy Remuxer 1.4.1 — Resume State

Last updated: 2026-08-20

## Reliability state

COMPLETE

## Authoritative source and protected artifacts

- Workspace/write scope: `C:\Users\Doug\Documents\ChatGPT\Topaz Video`
- Branch: `codex/transcoding-v1.4.0`
- Baseline commit: `4e687835a968cb02a551f3e8822c29c96a0b34d9`
- Governing patch requirements: `AVI_QUALITY_UI_V1_4_1_REQUIREMENTS.md`
- Prior verified state: `TRANSCODING_V1_4_RESUME_STATE.md`
- Protected prior release: `release-stream-copy-remuxer-v1.4.0`
- Release folder: `release-stream-copy-remuxer-v1.4.1`
- Release ZIP: `Stream-Copy-Remuxer-v1.4.1-Windows-x64.zip`
- Final QA: `qa\release-v1.4.1-onefile-final`
- EXE SHA-256: `996068ace3457917a2e90bea0dde40788b1a2fe10b428fcf534a5ce9c0bd382f`
- ZIP SHA-256: `0fc044d882f8867f03613957f46a502566d5bb993f1007d5d5bb9e7cfbd8c7c9`
- User-owned unrelated paths remain excluded: `Launch-Topaz-SLP-Benchmark.ps1`, `SLP26_HIGH_VRAM_INVESTIGATION_RESUME_STATE.md`, `slp_high_vram_override/`, and `tools/`.

## Declared change surface

- Container model, planning policy, CLI container choice, GUI encoder-dependent control layout, help/readme text, patch version, and directly related automated tests.
- Existing encoder commands, stream-copy safety, output verification, batch behavior, FFmpeg installation, and unrelated Topaz/SLP utilities are protected.

## Baseline evidence

- Relevant source hashes before this patch:
  - `stream_copy_remuxer/gui.py`: `7D63D616C3FF6D29FA1A7C84CA8AB3ADC5C485C9B95E0FF42E0FC35D5E5B4280`
  - `stream_copy_remuxer/models.py`: `105B0EB17A3B9431A8575F300DE498D4DA9C018DFDEE66249B9359D1EB25CE4A`
  - `stream_copy_remuxer/encoding.py`: `291F446D29A8B6CD7B9F7439B71DE7EBC0CE80C8BDD8FB687346F401BD903563`
  - `stream_copy_remuxer/planning.py`: `397F04B32F46EBBC3CFAD4CC929E0863276CFFE0DB14F8FAAF613B4F36ED4104`
  - `remux_main.py`: `56CF90EA75222B3284702A291FC170BB8E04B8DCA312B498AE8A568AB1E10036`
- Baseline command outside the Codex filesystem sandbox:
  - Python 3.11 release runtime, `python -m unittest tests.test_planning tests.test_gui`
  - Result: 25 tests passed.
- The same GUI subset inside the sandbox produced eight existing `can't find package tkdnd` errors; this matches the prior documented sandbox-only limitation and is not an application assertion failure.

## Acceptance checklist

- [x] Conditional Quality layout implemented and tested.
- [x] AVI Stream Copy GUI/model/planning/CLI support implemented and tested.
- [x] Real FFmpeg AVI operation verified.
- [x] Full regression suite passed with documented skips only.
- [x] Versioned packaged artifact passed exact-artifact verification.
- [x] Skeptical final audit completed without unresolved material findings.

## Changes made

- Added AVI to the Stream Copy container model, GUI dropdown, CLI, output naming, planning notes, and FFmpeg muxer selection.
- Compatible AVI mode retains video/audio and discloses omitted subtitle/attachment/data tracks; strict mode blocks known-incompatible extras before FFmpeg.
- Stream Copy, ProRes, and DNxHR now remove the Quality widgets from the grid and expand the encoder dropdown into the reclaimed space.
- CRF/CQ profiles restore the widgets with the correct label, range, and enabled/disabled state.
- Updated version/readme/release scripts and added focused unit, GUI, CLI, source self-test, packaged self-test, and real FFmpeg coverage.
- Generated a new versioned folder and ZIP without replacing v1.4.0 or touching the excluded user-owned paths.

## Latest validated checkpoint

- Final source suite on the Python 3.11/TkDND release runtime: **102 tests passed, 1 hardware-dependent NVENC test skipped**.
- Source self-test: `qa\source-v1.4.1-self-test.json` — passed, including real AVI output and conditional Quality GUI assertions.
- Candidate packaged self-test: `qa\release-v1.4.1-onefile-final\packaged-self-test.json` — passed.
- Fresh ZIP integrity: `qa\release-v1.4.1-onefile-final\zip-integrity.json` — passed every manifest size/hash check.
- Freshly extracted EXE self-test and dependency check: `extracted-self-test.json` and `extracted-dependency-check.json` — both passed and reported version 1.4.1 / FFmpeg 9.0.1.
- Rendered main-window preview was visually inspected; the inapplicable Quality area is absent and the encoder dropdown uses the reclaimed width.
- `python -m compileall` and `git diff --check` passed.
- Protected v1.4.0 hashes still match the prior record: EXE `6b62ddb01ba051363ba29c5da542a909a23651a0477f11615a43fbe68fb3297a`; ZIP `4f12c702183366c84f6c011c3182fc7a605e9a76594528eb6032abf5cf108d0f`.

## Failed or disqualified methods

- GUI tests cannot load TkDND inside the managed filesystem sandbox; use the approved Python 3.11 release runtime outside that sandbox for GUI gates.
- `python -m unittest discover -s tests -v` was disqualified because choosing `tests` as the discovery root strips package context and breaks relative test imports. Package-aware `python -m unittest` passed the complete suite.
- The single skipped hardware test is expected: this machine exposes `h264_nvenc` but its GPU/driver rejects the user-requested `lookahead_level 3`. No encoder setting was weakened.

## Remaining risks and untested conditions

- AVI accepts fewer codec/stream combinations than MKV. Each file still receives a disposable preflight; an incompatible selected video/audio codec fails safely without publishing output.
- Hardware encoder execution remains dependent on the installed GPU/driver and is unchanged by this patch.
- The standalone EXE is not Authenticode-signed.

## Exact next action

No implementation work remains. Use the v1.4.1 ZIP for distribution or the EXE in the v1.4.1 release folder for local testing. GitHub publishing was not performed in this patch.
