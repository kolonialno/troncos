from importlib import metadata

# Get version using this method
# https://github.com/python-poetry/poetry/issues/273#issuecomment-1103812336

OTEL_LIBRARY_NAME = "troncos"
OTEL_LIBRARY_VERSION = metadata.version(__package__)

del metadata  # avoids polluting the results of dir(__package__)
