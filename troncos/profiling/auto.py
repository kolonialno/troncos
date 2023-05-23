import logging

from troncos.profiling.bootstrap import start

logger = logging.getLogger(__name__)

logger.info("Enabling the profiler by auto import")

start_profiler = start.start_profiler
