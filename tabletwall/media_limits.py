"""Shared limits for managed image ingest (R1).

The HTTP/store side and the decoder subprocess must agree on the same numbers;
they live here so neither module has to import the other. These are provisional
operational bounds from the roadmap, not measured hardware capacity.
"""

PIPELINE_VERSION = 1

# Source admission (roadmap "Normalize before publication").
MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_SOURCE_PIXELS = 32_000_000

# Normalized output bounds. Both the long-edge ceiling and the pixel ceiling
# apply: a 4096-square image is 16.7 MP and is reduced further.
MAX_MASTER_EDGE = 4096
MAX_MASTER_PIXELS = 12_000_000
MAX_OBJECT_BYTES = 10 * 1024 * 1024
RENDITION_EDGES = (2048, 1024, 256)
JPEG_QUALITY = 90
THUMBNAIL_QUALITY = 82

# Decoder job bounds.
WORKER_TIMEOUT_S = 30
WORKER_MEMORY_BYTES = 512 * 1024 * 1024
WORKER_CPU_SECONDS = 25
MAX_WAITING_UPLOADS = 2
RECEIVE_TIMEOUT_S = 60

# Prerecorded video (R4). Ingest accepts only H.264 in MP4/MOV, remuxes it
# losslessly, and never transcodes. The caps are the roadmap's initial 250 MiB
# and ten minutes; the 1 s floor is the playlist validator's minimum dwell,
# because a video item's dwell is its duration.
VIDEO_PIPELINE_VERSION = 1
MAX_VIDEO_BYTES = 250 * 1024 * 1024
MAX_VIDEO_DURATION_MS = 600_000
MIN_VIDEO_DURATION_MS = 1_000
MAX_VIDEO_LONG_EDGE = 1920
MAX_VIDEO_SHORT_EDGE = 1080
MAX_VIDEO_FPS = 60.0
MAX_H264_LEVEL = 41
VIDEO_PROFILES = ("Constrained Baseline", "Main", "High")
VIDEO_WORKER_TIMEOUT_S = 120
VIDEO_RECEIVE_TIMEOUT_S = 600
VIDEO_TOOL_TIMEOUT_S = 90
MAX_PROBE_BYTES = 1024 * 1024

# Store bounds. The quota includes staging, job outputs and retained objects;
# the reserve keeps SQLite and the rest of the host writable.
QUOTA_BYTES = 2 * 1024 * 1024 * 1024
FREE_RESERVE_BYTES = 512 * 1024 * 1024
