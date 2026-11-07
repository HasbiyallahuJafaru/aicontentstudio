import os

# Motion layers drive a real browser (~30 s each). Off for the suite; test_motion turns it on where it means to.
os.environ.setdefault("ACS_NO_MOTION", "1")
