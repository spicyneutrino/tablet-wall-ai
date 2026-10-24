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

# Store bounds. The quota includes staging, job outputs and retained objects;
# the reserve keeps SQLite and the rest of the host writable.
QUOTA_BYTES = 2 * 1024 * 1024 * 1024
FREE_RESERVE_BYTES = 512 * 1024 * 1024
