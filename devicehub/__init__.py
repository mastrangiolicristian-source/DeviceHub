"""DeviceHub: ingestione GPS e provisioning per la piattaforma flotta."""

from .teltonika import AvlPacket, AvlRecord, ProtocolError

__all__ = ["AvlPacket", "AvlRecord", "ProtocolError"]
