"""Begrenzter FC03-Ersttest: drei bestätigte Kernblöcke, ohne Retries."""

import os
import sys

from backend.modbus import ModbusTcpClient
from backend.registers import CORE_PROFILE, decode_register_block


HOST = os.environ.get("MODBUS_HOST", "").strip()
if not HOST:
    raise SystemExit("MODBUS_HOST fehlt; Ziel nur aus privater Konfiguration setzen.")

client = ModbusTcpClient(HOST, port=502, deadline_seconds=3.0)

for index, block in enumerate(CORE_PROFILE):
    try:
        result = client.read(block)
        decoded = decode_register_block(block.offset, result.words)
        print(f"Offset {block.offset}/{block.count}: words={result.words}")
        for signal in decoded:
            print(f"  {signal.signal_id} = {signal.value} {signal.unit}")
    except Exception as exc:
        print(
            f"Abbruch bei Offset {block.offset}: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
