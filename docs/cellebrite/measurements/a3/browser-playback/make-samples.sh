#!/bin/bash
# Synthetic samples, one per container/codec group of 03 20.5 (3 s tone, 320x240 test pattern). No case material.
# Usage: make-samples.sh <empty dir>. Needs ffmpeg with libopus, libvorbis, libmp3lame, libx264, libx265, libsvtav1, libvpx.
set -e
cd "$1"
F="nice -n 15 ffmpeg -hide_banner -loglevel error -y"; A="-f lavfi -i sine=f=440:d=3"; V="-f lavfi -i testsrc=s=320x240:r=25:d=3"
$F $A -c:a libopus ogg_opus.ogg; $F $A -c:a libvorbis ogg_vorbis.ogg
$F $A -c:a aac m4a_aac.m4a; $F $A -c:a alac m4a_alac.m4a; $F $A -c:a libmp3lame mp3.mp3
$F $A -c:a aac caf_aac.caf; $F $A -c:a pcm_s16le caf_pcm.caf; $F $A -c:a libopus caf_opus.caf
$F $A -c:a alac caf_alac.caf; $F $A -c:a adpcm_ima_qt caf_ima.caf
$F $A -c:a pcm_s16be aiff.aiff; $F $A -c:a pcm_s16le wav_pcm.wav; $F $A -c:a pcm_mulaw wav_mulaw.wav
$F $V $A -c:v libx264 -pix_fmt yuv420p -c:a aac mp4_h264_aac.mp4
$F $V $A -c:v libx265 -tag:v hvc1 -pix_fmt yuv420p -c:a aac mp4_hevc_aac.mp4
$F $V -c:v libsvtav1 -pix_fmt yuv420p mp4_av1.mp4
$F $V $A -c:v h263 -s 352x288 -c:a aac 3gp_h263_aac.3gp
$F $V $A -c:v mpeg4 -c:a aac m4v_mpeg4.mp4
$F $V $A -c:v libvpx-vp9 -c:a libvorbis webm_vp9.webm
$F $V $A -c:v libx264 -pix_fmt yuv420p -c:a aac ts_h264_aac.ts
# ffmpeg has no AMR-NB encoder here: RFC 4867 storage format, 150 mode-0 frames of zero speech bits
python3 -c "open('amr_nb.amr','wb').write(b'#!AMR\n' + (bytes([0x04]) + bytes(12)) * 150)"
