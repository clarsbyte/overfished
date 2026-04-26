# Must run before overfished_api.main loads, so the BFF skips Auth0 in tests.
import os

os.environ["AUTH0_BYPASS"] = "1"
