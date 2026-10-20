"""Regista's private vision layer: broadcast video in, Regista event stream out.

Stages (each with an evaluation against the synthetic generator's exact ground truth):

- ``frames``     decode a video at a chosen rate and size
- ``shots``      shot agent: cut detection + a trained shot classifier -> ``camera_segment`` records
- ``pitch``      image <-> pitch mapping and the per-frame main-camera calibrator
- ``detect``     player discs, the ball, and team assignment by kit-colour clustering
- ``kitnumber``  kit-number reader (local digit classifier; Azure AI Vision OCR slot)
- ``identity``   identity agent: tracking, naming by number vote, cutaway appearances -> ``track`` / ``appearance``
- ``possession`` possession agent -> ``possession`` records
- ``pipeline``   ``run_vision(video, roster, out_dir)`` -> a validated match directory; ``compare_clips``
- ``agents``     the stages as Regista Agent roles and a Microsoft Agent Framework workflow
- ``truth``, ``dataset``, ``evaluate``  ground truth, rendered footage, training and evaluation (synthetic only)

Today every model is trained on Regista's own rendered broadcast (``regista.render``), where every
label is exact. Each module's docstring says what changes for real broadcast footage. See
docs/vision.md for measured numbers and how to reproduce them.

Optional dependencies (not in pyproject's core list): opencv-python-headless, scikit-learn, scipy, joblib.
"""
