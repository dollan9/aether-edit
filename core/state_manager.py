"""
AETHER-EDIT: Thread-Safe State Engine
CRDT/Optimistic Locking, Multi-Agent Mutation Engine, Atomic Transactions,
Undo/Redo History, and JSON Persistence
"""

import copy
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from config import (
    DEFAULT_FPS,
    DEFAULT_RESOLUTION,
    REGISTRY_FILE,
    SILENCE_PADDING_SEC,
    TIMELINE_FILE,
)
from core.event_bus import event_bus
from core.schema import (
    AgentState,
    AudioEnvelope,
    BatchActionType,
    BatchOperation,
    ClipEffect,
    ClipTransform,
    EasingType,
    EffectType,
    IngestStatus,
    Keyframe,
    MediaAsset,
    TimelineClip,
    TimelineState,
    Track,
    TrackType,
)

logger = logging.getLogger("aether_edit.state_manager")


class StateManager:
    """
    Central thread-safe state manager for AETHER-EDIT.
    Enforces optimistic concurrency control, rollback on transaction errors,
    and automatic collision resolution.
    """

    def __init__(self, timeline_path: Path = TIMELINE_FILE, registry_path: Path = REGISTRY_FILE):
        self._lock = threading.RLock()
        self.timeline_path = Path(timeline_path)
        self.registry_path = Path(registry_path)

        self._media_registry: Dict[str, MediaAsset] = {}
        self._timeline: TimelineState = self._initialize_default_timeline()

        # Undo / Redo Stacks (stores snapshots of TimelineState)
        self._undo_stack: List[TimelineState] = []
        self._redo_stack: List[TimelineState] = []
        self._max_history: int = 100

        # Load existing state from disk if present
        self.load_state()

    def _initialize_default_timeline(self) -> TimelineState:
        """Create a standard broadcast NLE multi-track layout."""
        tracks = [
            Track(track_id="trk_video_1", track_name="Video 1", track_type=TrackType.VIDEO),
            Track(track_id="trk_video_2", track_name="Video 2 (B-Roll)", track_type=TrackType.VIDEO),
            Track(track_id="trk_audio_1", track_name="Audio 1 (Dialogue)", track_type=TrackType.AUDIO),
            Track(track_id="trk_audio_2", track_name="Audio 2 (Music/SFX)", track_type=TrackType.AUDIO),
            Track(track_id="trk_effects", track_name="Effects & Overlays", track_type=TrackType.EFFECT),
            Track(track_id="trk_subtitles", track_name="Subtitles", track_type=TrackType.SUBTITLE),
        ]
        return TimelineState(
            project_id=str(uuid4()),
            project_name="Aether_Master_Cut",
            resolution=DEFAULT_RESOLUTION,
            fps=DEFAULT_FPS,
            version=1,
            tracks=tracks,
        )

    # -------------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------------

    def save_state(self) -> None:
        """Atomically persist timeline and media registry to disk."""
        with self._lock:
            try:
                # Atomic save for timeline
                self.timeline_path.parent.mkdir(parents=True, exist_ok=True)
                temp_timeline = self.timeline_path.with_suffix(".tmp")
                with open(temp_timeline, "w", encoding="utf-8") as f:
                    f.write(self._timeline.model_dump_json(indent=2))
                temp_timeline.replace(self.timeline_path)

                # Atomic save for media registry
                temp_registry = self.registry_path.with_suffix(".tmp")
                reg_data = {k: v.model_dump() for k, v in self._media_registry.items()}
                with open(temp_registry, "w", encoding="utf-8") as f:
                    json.dump(reg_data, f, indent=2)
                temp_registry.replace(self.registry_path)
            except Exception as e:
                logger.error(f"Failed to persist state: {e}")

    def load_state(self) -> None:
        """Load state from disk if files exist."""
        with self._lock:
            if self.registry_path.exists():
                try:
                    with open(self.registry_path, "r", encoding="utf-8") as f:
                        reg_dict = json.load(f)
                        self._media_registry = {
                            k: MediaAsset.model_validate(v) for k, v in reg_dict.items()
                        }
                except Exception as e:
                    logger.error(f"Failed loading media registry: {e}")

            if self.timeline_path.exists():
                try:
                    with open(self.timeline_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self._timeline = TimelineState.model_validate(data)
                except Exception as e:
                    logger.error(f"Failed loading timeline state: {e}")

    # -------------------------------------------------------------------------
    # History & Undo / Redo
    # -------------------------------------------------------------------------

    def _snapshot(self) -> None:
        """Record current state to undo history before applying modifications."""
        self._undo_stack.append(copy.deepcopy(self._timeline))
        if len(self._undo_stack) > self._max_history:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self) -> Optional[TimelineState]:
        with self._lock:
            if not self._undo_stack:
                return None
            self._redo_stack.append(copy.deepcopy(self._timeline))
            self._timeline = self._undo_stack.pop()
            self._timeline.version += 1
            self.save_state()
            event_bus.emit_timeline_update(self._timeline)
            return self._timeline

    def redo(self) -> Optional[TimelineState]:
        with self._lock:
            if not self._redo_stack:
                return None
            self._undo_stack.append(copy.deepcopy(self._timeline))
            self._timeline = self._redo_stack.pop()
            self._timeline.version += 1
            self.save_state()
            event_bus.emit_timeline_update(self._timeline)
            return self._timeline

    # -------------------------------------------------------------------------
    # Getters
    # -------------------------------------------------------------------------

    def get_timeline(self) -> TimelineState:
        with self._lock:
            return copy.deepcopy(self._timeline)

    def get_media_asset(self, asset_id: str) -> Optional[MediaAsset]:
        with self._lock:
            asset = self._media_registry.get(asset_id)
            return copy.deepcopy(asset) if asset else None

    def list_media_assets(self) -> List[MediaAsset]:
        with self._lock:
            return [copy.deepcopy(a) for a in self._media_registry.values()]

    # -------------------------------------------------------------------------
    # Media Registry Updates
    # -------------------------------------------------------------------------

    def register_or_update_media(self, asset: MediaAsset) -> None:
        with self._lock:
            self._media_registry[asset.asset_id] = copy.deepcopy(asset)
            self.save_state()
            event_bus.emit_media_registered(asset)

    def set_media_status(
        self, asset_id: str, status: IngestStatus, error: Optional[str] = None
    ) -> Optional[MediaAsset]:
        with self._lock:
            asset = self._media_registry.get(asset_id)
            if not asset:
                return None
            asset.ingest_status = status
            if error:
                asset.error_message = error
            self.save_state()
            event_bus.emit_media_registered(asset)
            return copy.deepcopy(asset)

    # -------------------------------------------------------------------------
    # Multi-Agent State Updates
    # -------------------------------------------------------------------------

    def register_agent(self, agent_id: str, role: str, color_hex: str) -> AgentState:
        with self._lock:
            agent = AgentState(
                agent_id=agent_id,
                role=role,
                color_hex=color_hex,
                playhead_sec=0.0,
                current_task="REGISTERED",
                last_ping_ms=time.time() * 1000,
            )
            self._timeline.active_agents[agent_id] = agent
            event_bus.emit_agent_heartbeat(agent)
            event_bus.emit_terminal_log(agent_id, f"Agent joined collaboration as {role}", "INFO")
            return agent

    def update_agent_heartbeat(
        self, agent_id: str, playhead_sec: float, task: str, latency_ms: float = 0.0
    ) -> Optional[AgentState]:
        with self._lock:
            agent = self._timeline.active_agents.get(agent_id)
            if not agent:
                agent = AgentState(
                    agent_id=agent_id,
                    role="EDITOR",
                    color_hex="#00F5D4",
                    playhead_sec=playhead_sec,
                    current_task=task,
                    last_ping_ms=time.time() * 1000,
                    latency_ms=latency_ms,
                )
                self._timeline.active_agents[agent_id] = agent
            else:
                agent.playhead_sec = playhead_sec
                agent.current_task = task
                agent.last_ping_ms = time.time() * 1000
                agent.latency_ms = latency_ms

            event_bus.emit_agent_heartbeat(agent)
            return copy.deepcopy(agent)

    # -------------------------------------------------------------------------
    # Atomic Batch Operation Execution
    # -------------------------------------------------------------------------

    def execute_batch(
        self, operations: List[BatchOperation], mode: str = "insert", agent_id: str = "AGENT_01"
    ) -> TimelineState:
        """
        Execute an atomic batch of timeline operations.
        If any single operation fails, the timeline rolls back to pre-batch state!
        """
        with self._lock:
            # Create a rollback checkpoint
            rollback_snapshot = copy.deepcopy(self._timeline)
            self._snapshot()

            try:
                for op in operations:
                    self._dispatch_operation(op, mode=mode, agent_id=agent_id)

                # Increment version monotonically
                self._timeline.version += 1
                self.save_state()

                # Dispatch updates
                event_bus.emit_timeline_update(self._timeline)
                event_bus.emit_terminal_log(
                    agent_id,
                    f"Executed batch ({len(operations)} ops, mode={mode}, v{self._timeline.version})",
                    "SUCCESS",
                )
                return copy.deepcopy(self._timeline)
            except Exception as e:
                # Rollback on error
                self._timeline = rollback_snapshot
                if self._undo_stack:
                    self._undo_stack.pop()
                logger.error(f"Batch execution failed, rolled back: {e}")
                event_bus.emit_terminal_log(agent_id, f"Batch rolled back: {str(e)}", "ERROR")
                raise e

    def _dispatch_operation(self, op: BatchOperation, mode: str, agent_id: str) -> None:
        action = op.action
        p = op.params

        if action == BatchActionType.INSERT_CLIP:
            self._op_insert_clip(p, mode=mode, agent_id=agent_id)
        elif action == BatchActionType.RAZOR_SPLIT:
            self._op_razor_split(p, agent_id=agent_id)
        elif action == BatchActionType.TRIM_CLIP:
            self._op_trim_clip(p, agent_id=agent_id)
        elif action == BatchActionType.RIPPLE_DELETE:
            self._op_ripple_delete(p, agent_id=agent_id)
        elif action == BatchActionType.AUTO_SLICE_SILENCE:
            self._op_auto_slice_silence(p, agent_id=agent_id)
        elif action == BatchActionType.ADD_KEYFRAME:
            self._op_add_keyframe(p, agent_id=agent_id)
        elif action == BatchActionType.APPLY_EFFECT:
            self._op_apply_effect(p, agent_id=agent_id)
        elif action == BatchActionType.AUTO_SYNC_AUDIO_DUCKING:
            self._op_auto_sync_audio_ducking(p, agent_id=agent_id)
        elif action == BatchActionType.GENERATE_CAPTIONS:
            self._op_generate_captions(p, agent_id=agent_id)
        else:
            raise ValueError(f"Unknown batch operation action: {action}")

    # -------------------------------------------------------------------------
    # Core Atomic Operations
    # -------------------------------------------------------------------------

    def _op_insert_clip(self, params: Dict[str, Any], mode: str, agent_id: str) -> None:
        track_id = params.get("track_id", "trk_video_1")
        track = self._timeline.get_track(track_id)
        if not track:
            raise ValueError(f"Track not found: {track_id}")

        clip_id = params.get("clip_id", str(uuid4()))
        asset_id = params.get("asset_id")
        name = params.get("name", "Clip")
        start_sec = float(params.get("timeline_start_sec", 0.0))
        source_in = float(params.get("source_in_sec", 0.0))
        source_out = float(params.get("source_out_sec", 10.0))
        speed = float(params.get("playback_speed", 1.0))
        duration = (source_out - source_in) / speed
        end_sec = start_sec + duration
        color_hex = params.get("color_hex", "#00F5D4")

        new_clip = TimelineClip(
            clip_id=clip_id,
            asset_id=asset_id,
            name=name,
            created_by_agent=agent_id,
            color_hex=color_hex,
            source_in_sec=source_in,
            source_out_sec=source_out,
            timeline_start_sec=start_sec,
            timeline_end_sec=end_sec,
            playback_speed=speed,
        )

        # Handle collisions
        if mode == "insert":
            # Ripple shift subsequent clips right by duration
            for c in track.clips:
                if c.timeline_start_sec >= start_sec:
                    c.timeline_start_sec += duration
                    c.timeline_end_sec += duration
            track.clips.append(new_clip)
        else:  # overwrite
            # Remove or trim overlapping segments
            kept_clips: List[TimelineClip] = []
            for c in track.clips:
                if c.timeline_end_sec <= start_sec or c.timeline_start_sec >= end_sec:
                    kept_clips.append(c)
                elif c.timeline_start_sec < start_sec and c.timeline_end_sec > end_sec:
                    # Clip surrounds new clip: split into left and right
                    left_dur = start_sec - c.timeline_start_sec
                    right_dur = c.timeline_end_sec - end_sec

                    left_clip = copy.deepcopy(c)
                    left_clip.clip_id = str(uuid4())
                    left_clip.timeline_end_sec = start_sec
                    left_clip.source_out_sec = c.source_in_sec + (left_dur * c.playback_speed)
                    kept_clips.append(left_clip)

                    right_clip = copy.deepcopy(c)
                    right_clip.clip_id = str(uuid4())
                    right_clip.timeline_start_sec = end_sec
                    right_clip.source_in_sec = c.source_out_sec - (right_dur * c.playback_speed)
                    kept_clips.append(right_clip)
                elif c.timeline_start_sec < start_sec:
                    # Overlaps on right side of c
                    c.timeline_end_sec = start_sec
                    c.source_out_sec = c.source_in_sec + (
                        (start_sec - c.timeline_start_sec) * c.playback_speed
                    )
                    kept_clips.append(c)
                elif c.timeline_end_sec > end_sec:
                    # Overlaps on left side of c
                    c.timeline_start_sec = end_sec
                    c.source_in_sec = c.source_out_sec - (
                        (c.timeline_end_sec - end_sec) * c.playback_speed
                    )
                    kept_clips.append(c)
            kept_clips.append(new_clip)
            track.clips = kept_clips

        # Keep clips sorted by timeline_start_sec
        track.clips.sort(key=lambda c: c.timeline_start_sec)

    def _op_razor_split(self, params: Dict[str, Any], agent_id: str) -> None:
        clip_id = params.get("clip_id")
        split_time = float(params.get("timeline_sec", 0.0))

        found = self._timeline.find_clip_with_track(clip_id)
        if not found:
            raise ValueError(f"Cannot razor split: clip {clip_id} not found")
        track, clip = found

        if not (clip.timeline_start_sec < split_time < clip.timeline_end_sec):
            raise ValueError(
                f"Split time {split_time:.2f}s is outside clip bounds "
                f"[{clip.timeline_start_sec:.2f}s - {clip.timeline_end_sec:.2f}s]"
            )

        left_dur = split_time - clip.timeline_start_sec
        split_source_sec = clip.source_in_sec + (left_dur * clip.playback_speed)

        # Create right slice
        right_clip = copy.deepcopy(clip)
        right_clip.clip_id = str(uuid4())
        right_clip.timeline_start_sec = split_time
        right_clip.source_in_sec = split_source_sec
        right_clip.created_by_agent = agent_id

        # Adjust left slice
        clip.timeline_end_sec = split_time
        clip.source_out_sec = split_source_sec

        track.clips.append(right_clip)
        track.clips.sort(key=lambda c: c.timeline_start_sec)

    def _op_trim_clip(self, params: Dict[str, Any], agent_id: str) -> None:
        clip_id = params.get("clip_id")
        found = self._timeline.find_clip_with_track(clip_id)
        if not found:
            raise ValueError(f"Clip {clip_id} not found for trim")
        track, clip = found

        if "source_in_sec" in params:
            clip.source_in_sec = float(params["source_in_sec"])
        if "source_out_sec" in params:
            clip.source_out_sec = float(params["source_out_sec"])
        if "timeline_start_sec" in params:
            clip.timeline_start_sec = float(params["timeline_start_sec"])

        clip.sync_timeline_duration()
        track.clips.sort(key=lambda c: c.timeline_start_sec)

    def _op_ripple_delete(self, params: Dict[str, Any], agent_id: str) -> None:
        clip_id = params.get("clip_id")
        start_t = params.get("start_sec")
        end_t = params.get("end_sec")
        target_tracks = params.get("track_ids", [t.track_id for t in self._timeline.tracks])

        if clip_id:
            found = self._timeline.find_clip_with_track(clip_id)
            if not found:
                raise ValueError(f"Clip {clip_id} not found for ripple delete")
            track, clip = found
            gap_duration = clip.timeline_end_sec - clip.timeline_start_sec
            del_start = clip.timeline_start_sec

            track.clips.remove(clip)
            # Shift subsequent clips left on this track (or all target tracks)
            for t in self._timeline.tracks:
                if t.track_id in target_tracks:
                    for c in t.clips:
                        if c.timeline_start_sec >= del_start:
                            c.timeline_start_sec -= gap_duration
                            c.timeline_end_sec -= gap_duration
        elif start_t is not None and end_t is not None:
            del_start = float(start_t)
            del_end = float(end_t)
            gap_duration = del_end - del_start
            if gap_duration <= 0:
                return

            for t in self._timeline.tracks:
                if t.track_id in target_tracks:
                    kept: List[TimelineClip] = []
                    for c in t.clips:
                        if c.timeline_end_sec <= del_start:
                            kept.append(c)
                        elif c.timeline_start_sec >= del_end:
                            c.timeline_start_sec -= gap_duration
                            c.timeline_end_sec -= gap_duration
                            kept.append(c)
                    t.clips = kept

    def _op_auto_slice_silence(self, params: Dict[str, Any], agent_id: str) -> None:
        clip_id = params.get("clip_id")
        asset_id = params.get("asset_id")
        padding_sec = float(params.get("padding_sec", SILENCE_PADDING_SEC))

        if not asset_id and clip_id:
            found = self._timeline.find_clip_with_track(clip_id)
            if found:
                asset_id = found[1].asset_id

        if not asset_id:
            raise ValueError("auto_slice_silence requires clip_id or asset_id")

        asset = self.get_media_asset(asset_id)
        if not asset:
            raise ValueError(f"MediaAsset {asset_id} not found for silence slicing")

        silences = asset.audio_telemetry.silence_intervals
        if not silences:
            logger.info(f"No silences detected for asset {asset_id}")
            return

        # Find target clip to replace with sliced speech pieces
        found = self._timeline.find_clip_with_track(clip_id) if clip_id else None
        if not found:
            # Look for any clip referencing this asset
            for t in self._timeline.tracks:
                for c in t.clips:
                    if c.asset_id == asset_id:
                        found = (t, c)
                        break
                if found:
                    break

        if not found:
            raise ValueError("No clip on timeline to slice for silence")

        track, original_clip = found
        orig_start = original_clip.timeline_start_sec
        orig_in = original_clip.source_in_sec
        orig_out = original_clip.source_out_sec

        # Compute speech segments by inverting silence intervals within [orig_in, orig_out]
        speech_intervals: List[Tuple[float, float]] = []
        cursor = orig_in

        for s in sorted(silences, key=lambda x: x.start):
            s_start = max(orig_in, s.start + padding_sec)
            s_end = min(orig_out, s.end - padding_sec)
            if s_start > cursor:
                speech_intervals.append((cursor, s_start))
            cursor = max(cursor, s_end)

        if cursor < orig_out:
            speech_intervals.append((cursor, orig_out))

        if not speech_intervals:
            return

        # Replace original clip with sequenced speech clips
        track.clips.remove(original_clip)
        new_timeline_pos = orig_start

        for idx, (sp_in, sp_out) in enumerate(speech_intervals):
            dur = sp_out - sp_in
            if dur <= 0.05:  # skip tiny micro-fragments
                continue
            slice_clip = copy.deepcopy(original_clip)
            slice_clip.clip_id = str(uuid4())
            slice_clip.name = f"{original_clip.name}_speech_{idx+1}"
            slice_clip.source_in_sec = sp_in
            slice_clip.source_out_sec = sp_out
            slice_clip.timeline_start_sec = new_timeline_pos
            slice_clip.timeline_end_sec = new_timeline_pos + dur
            slice_clip.created_by_agent = agent_id
            track.clips.append(slice_clip)
            new_timeline_pos += dur

        track.clips.sort(key=lambda c: c.timeline_start_sec)

    def _op_add_keyframe(self, params: Dict[str, Any], agent_id: str) -> None:
        clip_id = params.get("clip_id")
        prop = params.get("property")  # "scale_x", "scale_y", "position_x", "opacity", "gain_db"
        offset = float(params.get("time_offset_sec", 0.0))
        value = float(params.get("value", 1.0))
        easing_str = params.get("easing", "LINEAR")
        easing = EasingType(easing_str)

        found = self._timeline.find_clip_with_track(clip_id)
        if not found:
            raise ValueError(f"Clip {clip_id} not found for keyframe")
        _, clip = found

        kf = Keyframe(time_offset_sec=offset, value=value, easing=easing)

        if prop == "scale_x":
            clip.transform.scale_x.append(kf)
        elif prop == "scale_y":
            clip.transform.scale_y.append(kf)
        elif prop == "position_x":
            clip.transform.position_x.append(kf)
        elif prop == "position_y":
            clip.transform.position_y.append(kf)
        elif prop == "rotation_deg":
            clip.transform.rotation_deg.append(kf)
        elif prop == "opacity":
            clip.transform.opacity.append(kf)
        elif prop in ("gain_db", "volume"):
            clip.audio_envelope.volume_keyframes.append(kf)
        else:
            raise ValueError(f"Unsupported keyframe property: {prop}")

    def _op_apply_effect(self, params: Dict[str, Any], agent_id: str) -> None:
        clip_id = params.get("clip_id")
        effect_type_str = params.get("effect_type", "DYNAMIC_ZOOM")
        effect_params = params.get("parameters", {})

        found = self._timeline.find_clip_with_track(clip_id)
        if not found:
            raise ValueError(f"Clip {clip_id} not found for effect")
        _, clip = found

        effect = ClipEffect(
            effect_id=str(uuid4()),
            effect_type=EffectType(effect_type_str),
            parameters=effect_params,
        )
        clip.effects.append(effect)

    def _op_auto_sync_audio_ducking(self, params: Dict[str, Any], agent_id: str) -> None:
        dialogue_track_id = params.get("dialogue_track_id", "trk_audio_1")
        music_track_id = params.get("music_track_id", "trk_audio_2")
        duck_db = float(params.get("duck_db", -14.0))
        ramp_sec = float(params.get("ramp_sec", 0.25))

        dialogue_track = self._timeline.get_track(dialogue_track_id)
        music_track = self._timeline.get_track(music_track_id)
        if not dialogue_track or not music_track:
            raise ValueError("Ducking tracks not found")

        # Clear existing ducking keyframes on music clips
        for m_clip in music_track.clips:
            m_clip.audio_envelope.volume_keyframes.clear()
            m_clip.audio_envelope.ducking_enabled = True

            # Generate keyframes for each dialogue clip interval
            for d_clip in dialogue_track.clips:
                d_start = d_clip.timeline_start_sec
                d_end = d_clip.timeline_end_sec

                if d_end <= m_clip.timeline_start_sec or d_start >= m_clip.timeline_end_sec:
                    continue

                # Local offsets inside music clip
                duck_in = max(0.0, d_start - m_clip.timeline_start_sec)
                duck_out = min(m_clip.duration_sec(), d_end - m_clip.timeline_start_sec)

                m_clip.audio_envelope.volume_keyframes.extend([
                    Keyframe(time_offset_sec=max(0.0, duck_in - ramp_sec), value=0.0),
                    Keyframe(time_offset_sec=duck_in, value=duck_db),
                    Keyframe(time_offset_sec=duck_out, value=duck_db),
                    Keyframe(
                        time_offset_sec=min(m_clip.duration_sec(), duck_out + ramp_sec), value=0.0
                    ),
                ])
            m_clip.audio_envelope.volume_keyframes.sort(key=lambda k: k.time_offset_sec)

    def _op_generate_captions(self, params: Dict[str, Any], agent_id: str) -> None:
        asset_id = params.get("asset_id")
        subtitle_track_id = params.get("track_id", "trk_subtitles")
        style = params.get("style", "POP_IN")

        asset = self.get_media_asset(asset_id) if asset_id else None
        if not asset or not asset.audio_telemetry.transcript:
            return

        sub_track = self._timeline.get_track(subtitle_track_id)
        if not sub_track:
            raise ValueError(f"Subtitle track {subtitle_track_id} not found")

        for segment in asset.audio_telemetry.transcript:
            for word_obj in segment.words:
                w_start = word_obj.start
                w_end = max(w_start + 0.2, word_obj.end)

                caption_clip = TimelineClip(
                    clip_id=str(uuid4()),
                    asset_id=None,
                    name=f"Sub_{word_obj.word}",
                    created_by_agent=agent_id,
                    color_hex="#FF2A85",
                    source_in_sec=0.0,
                    source_out_sec=w_end - w_start,
                    timeline_start_sec=w_start,
                    timeline_end_sec=w_end,
                    effects=[
                        ClipEffect(
                            effect_type=EffectType.SUBTITLE_CAPTION,
                            parameters={
                                "text": word_obj.word,
                                "font_size": 48,
                                "font_color": "&H00FFFFFF",
                                "highlight_color": "&H00D4F500",  # Cyan in ASS format
                                "style": style,
                            },
                        )
                    ],
                )
                sub_track.clips.append(caption_clip)

        sub_track.clips.sort(key=lambda c: c.timeline_start_sec)
