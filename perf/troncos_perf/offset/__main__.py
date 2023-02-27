import json
import sys
import statistics

from troncos_perf import MAX_SETUP_TIME

filename = sys.argv[1]
new_filename = sys.argv[2]

with open(filename) as f:
    data = json.load(f)

for res in data['results']:
    res['times'] = [t - MAX_SETUP_TIME for t in res['times']]
    res['mean'] = statistics.mean(res['times'])
    res['median'] = statistics.median(res['times'])
    res['stddev'] = statistics.stdev(res['times'])
    res['min'] = res['min'] - MAX_SETUP_TIME
    res['max'] = res['max'] - MAX_SETUP_TIME

# Writing to sample.json
with open(new_filename, "w") as outfile:
    outfile.write(json.dumps(data, indent=4))
