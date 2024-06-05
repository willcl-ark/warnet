SUPPORTED_TAGS = [
    "26.0",
    "25.1",
    "24.2",
    "23.2",
    "22.2",
]
DEFAULT_TAG = SUPPORTED_TAGS[0]
WEIGHTED_TAGS = [
    tag for index, tag in enumerate(reversed(SUPPORTED_TAGS)) for _ in range(index + 1)
]
