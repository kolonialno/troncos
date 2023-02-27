import time
start_time = time.time()

import importlib
import sys
from troncos_perf import MAX_SETUP_TIME

# Setup params
FIB_NUMBER = 25

# Import test module
test_module = sys.argv[1]
print(f"Test module: {test_module}")
test_module = importlib.import_module(f"troncos_perf.{test_module}")

# Normalize setup time
setup_time = time.time() - start_time
print(f"Module setup time: {setup_time}")
assert setup_time < MAX_SETUP_TIME
while time.time() - start_time < MAX_SETUP_TIME:
    pass
print(f"Total setup time: {time.time() - start_time}")

# Run test
test_module.run(FIB_NUMBER)
test_module.cleanup()
print(f"Total run time: {time.time() - start_time}")
