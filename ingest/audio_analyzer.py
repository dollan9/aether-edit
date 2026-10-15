"""
AETHER-EDIT: Audio Telemetry Analyzer
Faster-Whisper Word-Level Transcriptions, FFmpeg RMS dB Curve,
Silence Detection (-38dB / >0.35s), and Loudness Spike Classification
"""

import logging
import re
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from config import (
    FFMPEG_PATH,
    SILENCE_MIN_DURATION_SEC,
    SILENCE_THRESHOLD_DB,
)
from core.schema import (
    AudioTelemetry,
    LoudnessSpike,
    SilenceInterval,
    TranscriptSegment,
    TranscriptWord,
)

logger = logging.getLogger("aether_edit.audio_analyzer")


class AudioAnalyzer:
    """Analyzes audio tracks for speech transcripts, silence boundaries, and energy curves."""

    def __init__(self, whisper_model_size: str = "base") -> None:
        self.whisper_model_size = whisper_model_size
        self._whisper_model = None

    def _get_whisper_model(self):
        """Lazy load Whisper model on first use."""
        if self._whisper_model is None:
            try:
                from faster_whisper import WhisperModel
                # Attempt GPU first, fallback to CPU
                try:
                    self._whisper_model = WhisperModel(
                        self.whisper_model_size, device="cuda", compute_type="float16"
                    )
                except Exception:
                    self._whisper_model = WhisperModel(
                        self.whisper_model_size, device="cpu", compute_type="int8"
                    )
            except Exception as e:
                logger.warning(f"Failed loading faster-whisper model: {e}")
                self._whisper_model = False
        return self._whisper_model if self._whisper_model else None

    def analyze_audio(
        self,
        input_path: Path,
        silence_threshold_db: float = SILENCE_THRESHOLD_DB,
        silence_min_dur_sec: float = SILENCE_MIN_DURATION_SEC,
    ) -> AudioTelemetry:
        """Run complete audio analysis suite."""
        telemetry = AudioTelemetry()

        # 1. Detect silences via FFmpeg silencedetect
        silences = self.detect_silences(
            input_path, threshold_db=silence_threshold_db, min_duration=silence_min_dur_sec
        )
        telemetry.silence_intervals = silences

        # 2. Extract RMS dB curve and loudness spikes
        rms_curve, spikes = self.extract_rms_and_spikes(input_path)
        telemetry.rms_db_curve = rms_curve
        telemetry.loudness_spikes = spikes

        # 3. Transcribe speech with word-level timestamps
        segments = self.transcribe_word_level(input_path)
        telemetry.transcript = segments

        return telemetry

    def detect_silences(
        self, input_path: Path, threshold_db: float = -38.0, min_duration: float = 0.35
    ) -> List[SilenceInterval]:
        """Use FFmpeg silencedetect filter to extract silent intervals."""
        silence_filter = f"silencedetect=n={threshold_db}dB:d={min_duration}"
        cmd = [
            FFMPEG_PATH,
            "-y",
            "-i", str(input_path.resolve()),
            "-af", silence_filter,
            "-f", "null",
            "-",
        ]

        intervals: List[SilenceInterval] = []
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=90)
            lines = res.stderr.splitlines()

            silence_start: Optional[float] = None
            for line in lines:
                if "silence_start:" in line:
                    match = re.search(r"silence_start:\s*([0-9.]+)", line)
                    if match:
                        silence_start = float(match.group(1))
                elif "silence_end:" in line and silence_start is not None:
                    match = re.search(r"silence_end:\s*([0-9.]+)", line)
                    if match:
                        silence_end = float(match.group(1))
                        dur = silence_end - silence_start
                        intervals.append(
                            SilenceInterval(
                                start=round(silence_start, 3),
                                end=round(silence_end, 3),
                                duration=round(dur, 3),
                                avg_db=round(threshold_db - 3.0, 1),
                            )
                        )
                        silence_start = None

        except Exception as e:
            logger.error(f"FFmpeg silencedetect error: {e}")

        return intervals

    def extract_rms_and_spikes(
        self, input_path: Path
    ) -> Tuple[List[List[float]], List[LoudnessSpike]]:
        """
        Decode raw 16kHz audio, compute RMS curve at 10Hz (every 100ms),
        and identify sudden energy transients/spikes.
        """
        cmd = [
            FFMPEG_PATH,
            "-y",
            "-i", str(input_path.resolve()),
            "-vn",
            "-ac", "1",
            "-ar", "16000",
            "-f", "f32le",
            "pipe:1",
        ]

        rms_curve: List[List[float]] = []
        spikes: List[LoudnessSpike] = []

        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
            if proc.returncode != 0 or not proc.stdout:
                return rms_curve, spikes

            samples = np.frombuffer(proc.stdout, dtype=np.float32)
            if len(samples) == 0:
                return rms_curve, spikes

            # 16000 Hz / 10 = 1600 samples per 100ms window
            window_size = 1600
            num_windows = len(samples) // window_size

            if num_windows == 0:
                return rms_curve, spikes

            windowed = samples[: num_windows * window_size].reshape((num_windows, window_size))
            # Calculate RMS
            rms_vals = np.sqrt(np.mean(np.square(windowed), axis=1))

            # Convert to decibels relative to full scale: 20 * log10(max(rms, 1e-6))
            eps = 1e-6
            db_vals = 20.0 * np.log10(np.maximum(rms_vals, eps))
            # Clip between -80 dB and 0 dB
            db_vals = np.clip(db_vals, -80.0, 0.0)

            for i, db in enumerate(db_vals):
                t = round(i * 0.1, 2)
                rms_curve.append([t, round(float(db), 1)])

            # Identify spikes (energy jump > 16dB compared to preceding 5-frame moving average)
            for i in range(2, len(db_vals) - 1):
                prev_baseline = np.mean(db_vals[max(0, i - 5) : i])
                current_db = db_vals[i]
                if current_db - prev_baseline >= 16.0 and current_db >= -18.0:
                    t = round(i * 0.1, 2)
                    classification = "impact"
                    if current_db > -3.0:
                        classification = "gunshot"
                    elif current_db > -8.0:
                        classification = "scream"
                    elif current_db > -12.0:
                        classification = "shout"

                    spikes.append(
                        LoudnessSpike(
                            timestamp=t,
                            peak_db=round(float(current_db), 1),
                            classification=classification,
                        )
                    )

        except Exception as e:
            logger.error(f"RMS & Spike extraction error: {e}")

        return rms_curve, spikes

    def transcribe_word_level(self, input_path: Path) -> List[TranscriptSegment]:
        """Execute Faster-Whisper to transcribe audio with word-level timestamps."""
        model = self._get_whisper_model()
        if not model:
            logger.info("Faster-whisper unavailable, skipping transcription.")
            return []

        segments_out: List[TranscriptSegment] = []
        try:
            whisper_segments, _ = model.transcribe(
                str(input_path.resolve()),
                word_timestamps=True,
                beam_size=3,
                vad_filter=True,
            )

            for seg in whisper_segments:
                word_objs: List[TranscriptWord] = []
                if seg.words:
                    for w in seg.words:
                        clean_word = w.word.strip()
                        if clean_word:
                            word_objs.append(
                                TranscriptWord(
                                    word=clean_word,
                                    start=round(float(w.start), 3),
                                    end=round(float(w.end), 3),
                                    confidence=round(float(w.probability), 2),
                                    speaker_id="SPEAKER_00",
                                )
                            )

                segments_out.append(
                    TranscriptSegment(
                        start=round(float(seg.start), 3),
                        end=round(float(seg.end), 3),
                        text=seg.text.strip(),
                        words=word_objs,
                    )
                )

        except Exception as e:
            logger.warning(f"Whisper transcription failed: {e}")

        return segments_out
