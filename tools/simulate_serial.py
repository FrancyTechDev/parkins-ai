import time, json, random
ts = int(time.time())
while True:
    ts += 1
    msg = {
        "type":"ref",
        "ts":ts,
        "rms_diff": 0.02 + random.random()*0.04,
        "band_4_6": 0.6 + random.random()*0.6,
        "peaks": random.randint(5, 30),
        "tremor_f": 4.0 + random.random()*2.0,
        "gsr": random.randint(450, 700),
        "batt": 3.8,
        "qf": 0
    }
    print(json.dumps(msg))
    time.sleep(0.1)