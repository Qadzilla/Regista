"""Test-wide isolation: tests never read or write the real human feedback in data/feedback."""

import os
import tempfile

os.environ["REGISTA_FEEDBACK_DIR"] = tempfile.mkdtemp(prefix="regista_test_feedback_")
