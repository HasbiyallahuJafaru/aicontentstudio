import os

# Motion layers drive a real browser (~30 s each). Off for the suite; test_motion turns it on where it means to.
os.environ.setdefault("ACS_NO_MOTION", "1")
# The repo .env holds real keys for manual runs; tests stay keyless (and free) unless a test sets one.
os.environ.setdefault("ACS_NO_DOTENV", "1")
