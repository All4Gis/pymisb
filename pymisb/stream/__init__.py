# Author: Fran Raga <franka1986@gmail.com>

"""Stream module — real-time KLV extraction from UDP/RTP/RTSP streams."""

from .engine import open_stream

__all__ = ["open_stream"]
