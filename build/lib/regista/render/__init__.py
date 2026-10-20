"""2D broadcast renderer: event and track streams in, watchable video out.

- ``regista.render.scene``  Scene: interpolated positions, captions, score, clock at any t
- ``regista.render.draw``   one frame at time t (pitch view, replays, closeups, crowd, HUD)
- ``regista.render.video``  parallel frame rendering and MP4/GIF writing
- ``python -m regista.render``        whole-match video
- ``python -m regista.render.clips``  per-clip videos and a reel for one player
"""

from regista.render.draw import Style, frame_info, render_frame
from regista.render.scene import Scene
from regista.render.video import render_video

__all__ = ["Scene", "Style", "frame_info", "render_frame", "render_video"]
