"""
AETHER-EDIT: Strict Pydantic v2 Atomic Data Schemas
Timeline, Tracks, Clips, Keyframes, Effects, and Multi-Modal Telemetry
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4
from pydantic import BaseModel, Field, field_validator


class IngestStatus(str, Enum):
    PENDING = "PENDING"
    GENERATING_PROXY = "GENERATING_PROXY"
    ANALYZING_AUDIO = "ANALYZING_AUDIO"
    ANALYZING_VISION = "ANALYZING_VISION"
    READY = "READY"
    ERROR = "ERROR"


class EasingType(str, Enum):
    LINEAR = "LINEAR"
    EASE_IN_OUT_CUBIC = "EASE_IN_OUT_CUBIC"
    BEZIER = "BEZIER"


class EffectType(str, Enum):
    DYNAMIC_ZOOM = "DYNAMIC_ZOOM"
    CAMERA_SHAKE = "CAMERA_SHAKE"
    COLOR_GRADE_LUT = "COLOR_GRADE_LUT"
    VIGNETTE = "VIGNETTE"
    BLUR_REGION = "BLUR_REGION"
    CHROMA_KEY = "CHROMA_KEY"
    GLITCH = "GLITCH"
    TEXT_OVERLAY = "TEXT_OVERLAY"
    SUBTITLE_CAPTION = "SUBTITLE_CAPTION"


class TrackType(str, Enum):
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    EFFECT = "EFFECT"
    SUBTITLE = "SUBTITLE"


class TransitionType(str, Enum):
    CROSSFADE = "CROSSFADE"
    DIP_TO_BLACK = "DIP_TO_BLACK"
    WHIP_PAN = "WHIP_PAN"
    GLITCH_CUT = "GLITCH_CUT"


class BatchActionType(str, Enum):
    INSERT_CLIP = "INSERT_CLIP"
    RAZOR_SPLIT = "RAZOR_SPLIT"
    TRIM_CLIP = "TRIM_CLIP"
    RIPPLE_DELETE = "RIPPLE_DELETE"
    AUTO_SLICE_SILENCE = "AUTO_SLICE_SILENCE"
    ADD_KEYFRAME = "ADD_KEYFRAME"
    APPLY_EFFECT = "APPLY_EFFECT"
    AUTO_SYNC_AUDIO_DUCKING = "AUTO_SYNC_AUDIO_DUCKING"
    GENERATE_CAPTIONS = "GENERATE_CAPTIONS"


# -----------------------------------------------------------------------------
# Media Telemetry Models
# -----------------------------------------------------------------------------

class TechnicalMeta(BaseModel):
    width: int = 1920
    height: int = 1080
    fps: float = 60.0
    duration_sec: float = 0.0
    total_frames: int = 0
    video_codec: str = "h264"
    audio_codec: str = "aac"
    sample_rate: int = 48000
    channels: int = 2


class SilenceInterval(BaseModel):
    start: float
    end: float
    duration: float
    avg_db: float


class LoudnessSpike(BaseModel):
    timestamp: float
    peak_db: float
    classification: str = "impact"


class TranscriptWord(BaseModel):
    word: str
    start: float
    end: float
    confidence: float = 1.0
    speaker_id: str = "SPEAKER_00"


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str
    words: List[TranscriptWord] = Field(default_factory=list)


class AudioTelemetry(BaseModel):
    waveform_peaks: List[float] = Field(default_factory=list)
    rms_db_curve: List[List[float]] = Field(default_factory=list)  # [timestamp_sec, db_float]
    silence_intervals: List[SilenceInterval] = Field(default_factory=list)
    loudness_spikes: List[LoudnessSpike] = Field(default_factory=list)
    transcript: List[TranscriptSegment] = Field(default_factory=list)


class SceneCut(BaseModel):
    scene_index: int
    start_frame: int
    end_frame: int
    start_sec: float
    end_sec: float
    avg_motion_score: float = 0.0
    dominant_rgb: List[int] = Field(default_factory=lambda: [0, 0, 0])


class BoundingBox(BaseModel):
    label: str  # "person" | "face" | "vehicle"
    confidence: float
    bbox_norm: List[float]  # [x1, y1, x2, y2] in normalized 0.0-1.0 coords


class VisualTelemetry(BaseModel):
    scene_cuts: List[SceneCut] = Field(default_factory=list)
    bounding_boxes: Dict[int, List[BoundingBox]] = Field(default_factory=dict)


class MediaAsset(BaseModel):
    asset_id: str = Field(default_factory=lambda: str(uuid4()))
    filename: str
    relative_path: str
    absolute_path: str
    file_hash: str
    proxy_path: Optional[str] = None
    technical_meta: TechnicalMeta = Field(default_factory=TechnicalMeta)
    ingest_status: IngestStatus = IngestStatus.PENDING
    error_message: Optional[str] = None
    audio_telemetry: AudioTelemetry = Field(default_factory=AudioTelemetry)
    visual_telemetry: VisualTelemetry = Field(default_factory=VisualTelemetry)


# -----------------------------------------------------------------------------
# Timeline Clip & Track Models
# -----------------------------------------------------------------------------

class Keyframe(BaseModel):
    time_offset_sec: float
    value: float
    easing: EasingType = EasingType.LINEAR


class ClipTransform(BaseModel):
    position_x: List[Keyframe] = Field(default_factory=lambda: [Keyframe(time_offset_sec=0.0, value=0.0)])
    position_y: List[Keyframe] = Field(default_factory=lambda: [Keyframe(time_offset_sec=0.0, value=0.0)])
    scale_x: List[Keyframe] = Field(default_factory=lambda: [Keyframe(time_offset_sec=0.0, value=1.0)])
    scale_y: List[Keyframe] = Field(default_factory=lambda: [Keyframe(time_offset_sec=0.0, value=1.0)])
    rotation_deg: List[Keyframe] = Field(default_factory=lambda: [Keyframe(time_offset_sec=0.0, value=0.0)])
    opacity: List[Keyframe] = Field(default_factory=lambda: [Keyframe(time_offset_sec=0.0, value=1.0)])


class AudioEnvelope(BaseModel):
    gain_db: float = 0.0
    fade_in_sec: float = 0.0
    fade_out_sec: float = 0.0
    volume_keyframes: List[Keyframe] = Field(default_factory=list)
    ducking_enabled: bool = False


class ClipEffect(BaseModel):
    effect_id: str = Field(default_factory=lambda: str(uuid4()))
    effect_type: EffectType
    parameters: Dict[str, Any] = Field(default_factory=dict)


class Transition(BaseModel):
    type: TransitionType = TransitionType.CROSSFADE
    duration_sec: float = 0.5


class TimelineClip(BaseModel):
    clip_id: str = Field(default_factory=lambda: str(uuid4()))
    asset_id: Optional[str] = None  # None for text / synthetic adjustment clips
    name: str
    created_by_agent: str = "AGENT_01"
    color_hex: str = "#00F5D4"
    source_in_sec: float = 0.0
    source_out_sec: float = 10.0
    timeline_start_sec: float = 0.0
    timeline_end_sec: float = 10.0
    playback_speed: float = 1.0
    transform: ClipTransform = Field(default_factory=ClipTransform)
    audio_envelope: AudioEnvelope = Field(default_factory=AudioEnvelope)
    effects: List[ClipEffect] = Field(default_factory=list)
    transition_in: Optional[Transition] = None
    transition_out: Optional[Transition] = None

    @field_validator("playback_speed")
    @classmethod
    def validate_speed(cls, v: float) -> float:
        if v <= 0.01:
            raise ValueError("Playback speed must be strictly positive")
        return v

    def duration_sec(self) -> float:
        return self.timeline_end_sec - self.timeline_start_sec

    def sync_timeline_duration(self) -> None:
        """Recalculate timeline_end_sec based on source duration and playback speed."""
        source_dur = max(0.0, self.source_out_sec - self.source_in_sec)
        self.timeline_end_sec = self.timeline_start_sec + (source_dur / self.playback_speed)


class Track(BaseModel):
    track_id: str
    track_name: str
    track_type: TrackType
    muted: bool = False
    locked: bool = False
    volume_db: float = 0.0
    clips: List[TimelineClip] = Field(default_factory=list)

    def find_clip(self, clip_id: str) -> Optional[TimelineClip]:
        for clip in self.clips:
            if clip.clip_id == clip_id:
                return clip
        return None


class AgentState(BaseModel):
    agent_id: str
    role: str = "EDITOR"
    color_hex: str = "#00F5D4"
    playhead_sec: float = 0.0
    current_task: str = "IDLE"
    last_ping_ms: float = 0.0
    latency_ms: float = 0.0


class TimelineState(BaseModel):
    project_id: str = Field(default_factory=lambda: str(uuid4()))
    project_name: str = "Aether_Project"
    resolution: Tuple[int, int] = (1920, 1080)
    fps: float = 60.0
    version: int = 1
    active_agents: Dict[str, AgentState] = Field(default_factory=dict)
    tracks: List[Track] = Field(default_factory=list)

    def total_duration_sec(self) -> float:
        max_t = 0.0
        for track in self.tracks:
            for clip in track.clips:
                if clip.timeline_end_sec > max_t:
                    max_t = clip.timeline_end_sec
        return max_t

    def get_track(self, track_id: str) -> Optional[Track]:
        for t in self.tracks:
            if t.track_id == track_id:
                return t
        return None

    def find_clip_with_track(self, clip_id: str) -> Optional[Tuple[Track, TimelineClip]]:
        for t in self.tracks:
            for c in t.clips:
                if c.clip_id == clip_id:
                    return t, c
        return None


# -----------------------------------------------------------------------------
# Batch Operation Request Schema
# -----------------------------------------------------------------------------

class BatchOperation(BaseModel):
    action: BatchActionType
    params: Dict[str, Any] = Field(default_factory=dict)


class BatchRequest(BaseModel):
    mode: str = "insert"  # "insert" | "overwrite"
    operations: List[BatchOperation] = Field(default_factory=list)


class RenderRequest(BaseModel):
    output_filename: Optional[str] = None
    resolution: Optional[Tuple[int, int]] = None
    fps: Optional[float] = None
    encoder: Optional[str] = None  # "h264_nvenc" | "libx264"
    burn_subtitles: bool = True
