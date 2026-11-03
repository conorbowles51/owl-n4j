# 03 20.5: which browsers play which phone media groups

Measured 2026-11-03 on the deploy box. One synthetic file per container/codec group (`make-samples.sh`), served over
plain `http://127.0.0.1` with byte ranges (`serve.py`, Starlette `StaticFiles`, as the app serves folder files), and
played in each browser by `play.cjs` through `index.html`: the element loads (`loadeddata`) or reports an error,
plays muted for 1.5 s, and seeks to 2 s. "Picture" is `videoWidth > 0` after playing; a video that plays with
width 0 plays its sound with no picture. Raw answers: `results.json`.

Browsers: Chromium 145.0.7632.6 (Playwright 1.58.2 `chromium` channel, Chrome for Testing build, Linux) and
Firefox 146.0.1 (Playwright build, Linux). WebKit (Playwright 2248) did not start on this box (system libraries it
needs are not installed). Safari, Chrome and Edge on Windows or macOS, and phones, are not measured: there is no
such machine here. Firefox on Linux decodes H.264, AAC and HEVC through the system's FFmpeg libraries, so its HEVC
answer below is this box's, not Firefox on Windows or macOS.

| Group (03 20.5 count on the 14 server reports) | Sample | Chromium 145 | Firefox 146 |
|---|---|---|---|
| Ogg Opus (16,980) | `ogg_opus.ogg` | plays, seeks | plays, seeks |
| Ogg Vorbis (1,465) | `ogg_vorbis.ogg` | plays, seeks | plays, seeks |
| AAC-only MP4 / M4A (11,404) | `m4a_aac.m4a` | plays, seeks | plays, seeks |
| ALAC in MP4 (14) | `m4a_alac.m4a` | does not play (demuxer error) | does not play (metadata error) |
| MP3 (3,066) | `mp3.mp3` | plays, seeks | plays, seeks |
| H.264 in MP4 (11,796) | `mp4_h264_aac.mp4` | plays with picture, seeks | plays with picture, seeks |
| HEVC in MP4 (4,701) | `mp4_hevc_aac.mp4` | sound only, no picture | plays with picture (system decoder) |
| AV1 in MP4 (3,280) | `mp4_av1.mp4` | plays with picture, seeks | plays with picture, seeks |
| VP9 in WebM (500) | `webm_vp9.webm` | plays with picture, seeks | plays with picture, seeks |
| MPEG-4 Part 2 (`m4v`, 11) | `m4v_mpeg4.mp4` | sound only, no picture | sound only, no picture |
| H.263 in MP4/3GP (79) | `3gp_h263_aac.3gp` | sound only, no picture | does not play (metadata error) |
| MPEG-TS H.264 (262) | `ts_h264_aac.ts` | does not play | does not play |
| CAF, any codec (5,023: AAC, PCM, Opus, ALAC, IMA ADPCM) | `caf_*.caf` (5) | none plays | none plays |
| AIFF PCM (825) | `aiff.aiff` | does not play | does not play |
| AMR-NB (1,515) | `amr_nb.amr` | does not play | does not play |
| WAV PCM and mu-law (707) | `wav_pcm.wav`, `wav_mulaw.wav` | plays, seeks | plays, seeks |
| Unrecognised by ffprobe (5,030) | none: no container a browser knows | not tested | not tested |

Groups neither measured browser plays (sound and picture): CAF, AMR, AIFF, MPEG-TS, ALAC, H.263, MPEG-4 Part 2, and
HEVC in Chromium (no picture). These are the formats 03 section 8.3's converted copy has to cover; a video that
plays with no picture counts as not playable, so the player has to check the picture, not only an error.

To repeat: `make-samples.sh <dir>`, copy `index.html` into it, `python serve.py <dir> 18931`, then
`node play.cjs <frontend_v2 dir> <dir> http://127.0.0.1:18931/index.html results.json` (after
`npx playwright install chromium firefox webkit`).
