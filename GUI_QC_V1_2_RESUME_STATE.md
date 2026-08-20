# Stream Copy Remuxer v1.2.0 — GUI QC Resume State

Last updated: 2026-08-17

## Current state

- Reliability state: **VERIFIED**; every applicable acceptance and exact-artifact gate passed.
- Project root and writable scope: `C:\Users\Doug\Documents\ChatGPT\Topaz Video`.
- Complete acceptance checklist: `GUI_QC_V1_2_REQUIREMENTS.md`.
- Target release: v1.2.0 for Windows 10/11 x64.
- Protected v1.1.2 artifacts remain unchanged:
  - EXE SHA-256: `ebf3626bbba9f84b329ce17d7991763bc800789b089af7073380921e67d31521`.
  - ZIP SHA-256: `3a16da37254dfcf2b9d4239e67e3a6e75bc96277a5694ae5315b7d0f2a7b04a8`.
  - Baseline source-manifest SHA-256: `da90a2723dcd97f6ea0a481dfc0c56a20de6cdb9b3f6dce0ead58af50c421deb`.

## Confirmed cause and implementation

- The user's crashing executable exactly matches protected v1.1.2.
- Windows Application Error 1000 recorded the real crash at 2026-08-17 11:53:05 in `ucrtbase.dll`, exception `0xc0000409`, report ID `3e6be82b-52f5-4acf-bd8f-9f61ef8e7f80`.
- The disqualified Python/ctypes WNDPROC subclass has been deleted. Production drag-and-drop now uses TkinterDnD2 0.6.2/TkDND OLE2 and Tcl-list parsing with deferred queue mutation.
- The GUI now has a single-line description, DPI-aware readable rows and headings, filename-only source cells, a table `Compatibility` column, no output-path column, no custom output-folder controls, and a bounded Details region.
- GUI outputs are fixed beside each source with `_remux`, `_remux_2`, and later collision-safe suffixes. CLI `--output` remains explicit.
- The Streams dropdown explicitly states that Video + audio excludes subtitle, attachment, and data streams while retaining separately mapped metadata and chapters.
- Startup automatically discovers FFmpeg/FFprobe. The manual Change FFmpeg control is gone.
- The background release checker currently resolves official FFmpeg 9.0.1, released 2026-08-12. The value is fetched dynamically rather than permanently hard-coded.
- The optional installer requires confirmation, restricts downloads and redirects to the expected HTTPS provider, validates release metadata and advertised size, verifies SHA-256, rejects unsafe/malformed/incomplete ZIPs, validates matching FFmpeg and FFprobe versions, and promotes into `ffmpeg\<version>\bin` without overwriting.

## Exact-source validation checkpoint

- Native warnings-as-errors suite: **PASS**, 54 tests in 4.984 seconds.
- Bytecode compilation with warnings-as-errors: **PASS**.
- Final exact-source self-test: `qa\source-self-test-v1.2.0-exact-final.json`.
  - Overall: **PASS**; version 1.2.0.
  - 27 top-level checks passed.
  - FFV1/MKV to MP4 and MPEG-4/AVI to MKV batch: 2 complete, 0 failed.
  - GUI/TkDND registration: **PASS**, TkDND runtime 2.10.1.
  - 100%, 150%, and 200% layout audit: **PASS** for one-line description, padded rows, readable headings, and bounded Details height.
- Final live installer smoke: `qa\ffmpeg-installer-smoke-v1.2.0-final.json`.
  - Overall: **PASS**.
  - Release: FFmpeg 9.0.1.
  - Download: 111,253,802 bytes, matching advertised length.
  - Published/verified SHA-256: `fec81ae03971d9dd4be3ebe02e263bd2ec1d789483f931bdba5f5715e65da2e9`.
  - Both tools installed and validated; license preserved; existing install reused without network; no staging leftovers.
- Visual QA image: `qa\gui-preview-v1.2.0-working-4.png`; inspected and accepted for the requested layout changes.

## Exact delivered artifacts and package validation

- Standalone release folder: `release-stream-copy-remuxer-v1.2.0`.
- Standalone EXE:
  - Size: 11,879,225 bytes.
  - SHA-256: `d5604a07bf987dacfecbe51e654aa3f3c15c4b8166e6382a2ced955b3af74873`.
  - Authenticode: `NotSigned` (documented limitation).
- Release ZIP: `Stream-Copy-Remuxer-v1.2.0-Windows-x64.zip`.
  - Size: 11,660,642 bytes.
  - SHA-256: `cf8fa77c42823a58818b8359a3420d84d5b4c0f8e85ed26674725f3721da67bc`.
- Staged packaged self-test: `qa\release-v1.2.0-onefile-final\packaged-self-test.json`: **PASS**.
- Fresh ZIP integrity: `qa\release-v1.2.0-onefile-final\zip-integrity.json`: **PASS**, 8 actual and 8 expected files.
- Freshly extracted exact-EXE self-test: `qa\release-v1.2.0-onefile-final\packaged-self-test-from-zip.json`: **PASS**.
  - TkDND 2.10.1 registered.
  - 100%/150%/200% layout checks passed.
  - Two-file batch completed with 0 failures.
- Final skeptical audit: `qa\release-v1.2.0-onefile-final\final-audit.json`: **PASS**.
  - Release EXE matches the freshly extracted EXE and release manifest.
  - All source, staged, archive, extracted, layout, batch, installer, and protected-release checks passed.
  - Twelve production Python files scanned with zero unsafe WNDPROC callback hits.
  - FFmpeg/FFprobe are not bundled; installer support is enabled.
- Final source manifest: `qa\release-v1.2.0-onefile-final\source_manifest.json`; it excludes itself by design.

## Failed or superseded methods

- The v1.1.2 synthetic `WM_DROPFILES` self-test passed but did not expose the external Explorer native fast-fail; it is not accepted as sufficient proof.
- The v1.1.2 Python/ctypes WNDPROC subclass is disqualified and removed, not patched.
- A cached search result claiming FFmpeg 8.1.2 was current was superseded by the direct official page and provider metadata confirming 9.0.1.
- The first real installer smoke validated the archive and tools but a short-lived Windows scanner lock blocked the staging-folder rename. Same-volume promotion now uses a bounded retry; the subsequent three live installer smokes passed.
- Early GUI preview captures were blank or clipped; `qa\gui-preview-v1.2.0-working-4.png` supersedes them.
- The first freshly extracted EXE command used an unquoted absolute report path containing a space, so PowerShell split the argument and the app correctly exited with usage code 2 before testing. The correctly passed relative path then completed the exact extracted-EXE self-test successfully.
- The first generated final-audit report used an invalid PowerShell collection addition and did not scan the full package. It was deleted and regenerated with terminating errors; the accepted report scans all 12 production Python files.

## Residual risks and limitations

- A synthetic drop cannot reproduce every Explorer timing condition, but the unsafe native callback architecture is absent, the maintained OLE2 backend is packaged, repeated multi-file dispatch passes, and both packaged self-tests confirm TkDND registration.
- FFmpeg builds with nonnumeric git-only version strings cannot be reliably ordered against a stable number; the GUI conservatively offers the current stable installer.
- App-local installation requires a writable extracted app folder and internet access.
- The standalone EXE is not Authenticode-signed unless a signing identity is supplied.

## Completion status

- Every checkbox in `GUI_QC_V1_2_REQUIREMENTS.md` is complete.
- No unresolved material defect remains in the exact delivered v1.2.0 artifacts.
- No further implementation or verification action is pending; the next action is user delivery/use.
