"""
AETHER-EDIT: Deterministic FFmpeg Filter Graph Compiler
Compiles TimelineState into an optimized -filter_complex_script (filter_complex.txt),
dynamic .ass karaoke subtitle scripts, multi-input mappings, zooms, transitions,
audio ducking curves, and EBU R128 loudness normalization.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config import DEFAULT_FPS, DEFAULT_RESOLUTION, EXPORTS_DIR
from core.schema import EffectType, TimelineClip, TimelineState, TrackType
from core.state_manager import StateManager

logger = logging.getLogger("aether_edit.filter_graph")


class FilterGraphCompiler:
    """Translates TimelineState models directly into deterministic FFmpeg filter scripts."""

    def __init__(self, state_manager: StateManager, exports_dir: Path = EXPORTS_DIR) -> None:
        self.state_manager = state_manager
        self.exports_dir = Path(exports_dir)
        self.exports_dir.mkdir(parents=True, exist_ok=True)

    def compile(
        self,
        timeline: Optional[TimelineState] = None,
        output_name: str = "render_master",
        burn_subtitles: bool = True,
    ) -> Tuple[List[str], Path, Optional[Path], float]:
        """
        Compiles the current timeline state into:
        1. List of input file paths for `-i`
        2. Path to generated `filter_complex.txt`
        3. Path to generated `subtitles.ass` (if subtitle track has clips)
        4. Total timeline duration in seconds
        """
        if timeline is None:
            timeline = self.state_manager.get_timeline()

        width, height = timeline.resolution or DEFAULT_RESOLUTION
        fps = timeline.fps or DEFAULT_FPS
        total_duration = max(1.0, timeline.total_duration_sec())

        # 1. Collect all unique MediaAssets used in timeline
        input_files: List[str] = []
        asset_to_input_idx: Dict[str, int] = {}

        for track in timeline.tracks:
            for clip in track.clips:
                if clip.asset_id and clip.asset_id not in asset_to_input_idx:
                    asset = self.state_manager.get_media_asset(clip.asset_id)
                    if asset and Path(asset.absolute_path).exists():
                        asset_to_input_idx[clip.asset_id] = len(input_files)
                        input_files.append(asset.absolute_path)

        filter_lines: List[str] = []

        # 2. Base Canvas Generator (Black background for total duration)
        filter_lines.append(
            f"color=c=black:s={width}x{height}:r={fps}:d={total_duration:.3f}[base_canvas];"
        )
        current_video_layer = "base_canvas"

        video_clip_counter = 0
        audio_stream_labels: List[str] = []

        # 3. Process Video Tracks (bottom-to-top)
        for track in timeline.tracks:
            if track.track_type != TrackType.VIDEO or track.muted:
                continue

            for clip in sorted(track.clips, key=lambda c: c.timeline_start_sec):
                if not clip.asset_id or clip.asset_id not in asset_to_input_idx:
                    continue

                in_idx = asset_to_input_idx[clip.asset_id]
                video_clip_counter += 1
                c_lbl = f"v_clip_{video_clip_counter}"

                # Calculate trim and PTS
                trim_filter = (
                    f"[{in_idx}:v]trim=start={clip.source_in_sec:.3f}:end={clip.source_out_sec:.3f},"
                    f"setpts=(PTS-STARTPTS)/{clip.playback_speed:.3f}[{c_lbl}_trim];"
                )
                filter_lines.append(trim_filter)

                # Scaling and fit into canvas
                scale_fit = (
                    f"[{c_lbl}_trim]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                    f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1[{c_lbl}_scaled];"
                )
                filter_lines.append(scale_fit)

                # Check for dynamic punch-in zoom effect or scale keyframes
                zoomed_lbl = f"{c_lbl}_scaled"
                has_zoom = any(
                    e.effect_type == EffectType.DYNAMIC_ZOOM for e in clip.effects
                ) or any(k.value > 1.0 for k in clip.transform.scale_x)

                if has_zoom:
                    zoom_factor = 1.25
                    for e in clip.effects:
                        if e.effect_type == EffectType.DYNAMIC_ZOOM:
                            zoom_factor = float(e.parameters.get("zoom_factor", 1.25))
                    for k in clip.transform.scale_x:
                        if k.value > 1.0:
                            zoom_factor = max(zoom_factor, k.value)

                    crop_w = int(width / zoom_factor)
                    crop_h = int(height / zoom_factor)
                    zoom_filter = (
                        f"[{zoomed_lbl}]crop={crop_w}:{crop_h}:(iw-{crop_w})/2:(ih-{crop_h})/2,"
                        f"scale={width}:{height}[{c_lbl}_zoomed];"
                    )
                    filter_lines.append(zoom_filter)
                    zoomed_lbl = f"{c_lbl}_zoomed"

                # Overlay clip onto current composite layer
                next_video_layer = f"v_comp_{video_clip_counter}"
                overlay_filter = (
                    f"[{current_video_layer}][{zoomed_lbl}]overlay="
                    f"x=0:y=0:enable='between(t,{clip.timeline_start_sec:.3f},{clip.timeline_end_sec:.3f})':"
                    f"eof_action=pass[{next_video_layer}];"
                )
                filter_lines.append(overlay_filter)
                current_video_layer = next_video_layer

        # 4. Process Subtitles via ASS burning
        ass_path: Optional[Path] = None
        subtitle_track = next(
            (t for t in timeline.tracks if t.track_type == TrackType.SUBTITLE and not t.muted), None
        )

        if burn_subtitles and subtitle_track and subtitle_track.clips:
            ass_path = self.exports_dir / f"{output_name}_subs.ass"
            self._generate_ass_script(subtitle_track.clips, width, height, ass_path)
            # Escape path for FFmpeg filter on Windows
            clean_ass_path = str(ass_path.resolve()).replace("\\", "/").replace(":", "\\:")
            sub_layer = f"{current_video_layer}_sub"
            filter_lines.append(f"[{current_video_layer}]ass='{clean_ass_path}'[{sub_layer}];")
            current_video_layer = sub_layer

        # Rename final video stream
        filter_lines.append(f"[{current_video_layer}]null[outv];")

        # 5. Process Audio Tracks
        audio_clip_counter = 0
        for track in timeline.tracks:
            if track.track_type not in (TrackType.AUDIO, TrackType.VIDEO) or track.muted:
                continue

            for clip in track.clips:
                if not clip.asset_id or clip.asset_id not in asset_to_input_idx:
                    continue

                in_idx = asset_to_input_idx[clip.asset_id]
                audio_clip_counter += 1
                a_lbl = f"a_clip_{audio_clip_counter}"

                # atrim and asetpts
                a_trim = (
                    f"[{in_idx}:a]atrim=start={clip.source_in_sec:.3f}:end={clip.source_out_sec:.3f},"
                    f"asetpts=PTS-STARTPTS[{a_lbl}_trim];"
                )
                filter_lines.append(a_trim)

                # Volume adjustment & ducking keyframes
                vol_expr = "1.0"
                if clip.audio_envelope.volume_keyframes:
                    # Construct time-evaluated volume piecewise curve
                    pieces: List[str] = []
                    for kf in clip.audio_envelope.volume_keyframes:
                        # Convert dB to linear amplitude: 10^(dB/20)
                        lin_amp = 10.0 ** (kf.value / 20.0)
                        pieces.append(f"if(lt(t,{kf.time_offset_sec:.3f}),{lin_amp:.4f}")
                    nested_if = "1.0"
                    for p in reversed(pieces):
                        nested_if = f"{p},{nested_if})"
                    vol_expr = nested_if
                elif clip.audio_envelope.gain_db != 0.0:
                    lin_amp = 10.0 ** (clip.audio_envelope.gain_db / 20.0)
                    vol_expr = f"{lin_amp:.4f}"

                vol_filter = (
                    f"[{a_lbl}_trim]volume=eval=frame:volume='{vol_expr}'[{a_lbl}_vol];"
                )
                filter_lines.append(vol_filter)

                # Delay audio to timeline start position (adelay takes milliseconds)
                delay_ms = int(clip.timeline_start_sec * 1000)
                delay_filter = (
                    f"[{a_lbl}_vol]adelay={delay_ms}|{delay_ms}[{a_lbl}_delayed];"
                )
                filter_lines.append(delay_filter)
                audio_stream_labels.append(f"[{a_lbl}_delayed]")

        # 6. Mix Audio Streams and Apply EBU R128 Loudness Normalization
        if audio_stream_labels:
            amix_in = "".join(audio_stream_labels)
            filter_lines.append(
                f"{amix_in}amix=inputs={len(audio_stream_labels)}:duration=longest:dropout_transition=0[a_mixed];"
            )
            # Normalize to standard -14 LUFS broadcast spec
            filter_lines.append(
                "[a_mixed]loudnorm=I=-14:TP=-1.5:LRA=11[outa]"
            )
        else:
            # Generate silent stereo audio stream matching video duration
            filter_lines.append(
                f"anullsrc=r=48000:cl=stereo,atrim=duration={total_duration:.3f}[outa]"
            )

        # 7. Write filter_complex.txt to disk
        filter_script_path = self.exports_dir / f"{output_name}_filter_complex.txt"
        with open(filter_script_path, "w", encoding="utf-8") as f:
            f.write("\n".join(filter_lines))

        return input_files, filter_script_path, ass_path, total_duration

    def _generate_ass_script(
        self, clips: List[TimelineClip], width: int, height: int, output_file: Path
    ) -> None:
        """Generate high-aesthetic Advanced SubStation Alpha subtitle file with pop-in karaoke styling."""
        ass_header = f"""[Script Info]
Title: AETHER-EDIT Automated Captions
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Segoe UI,54,&H00FFFFFF,&H00D4F500,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,3.5,2.0,2,20,20,80,1
Style: PopIn,Segoe UI Black,62,&H0000F5D4,&H00FFFFFF,&H00000000,&HA0000000,-1,0,0,0,105,105,0,0,1,4.0,2.5,2,20,20,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        events: List[str] = []
        for c in clips:
            text = c.name.replace("Sub_", "")
            for eff in c.effects:
                if eff.effect_type == EffectType.SUBTITLE_CAPTION:
                    text = eff.parameters.get("text", text)

            start_tc = self._format_ass_time(c.timeline_start_sec)
            end_tc = self._format_ass_time(c.timeline_end_sec)
            # Add subtle animated zoom / pop-in scale tag
            line = f"Dialogue: 0,{start_tc},{end_tc},PopIn,,0,0,0,,{{\\t(0,80,\\fscx115\\fscy115)\\t(80,180,\\fscx100\\fscy100)}}{text}"
            events.append(line)

        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(ass_header + "\n".join(events) + "\n")

    @staticmethod
    def _format_ass_time(sec: float) -> str:
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = int(sec % 60)
        cs = int(round((sec - int(sec)) * 100))
        if cs >= 100:
            cs = 99
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
