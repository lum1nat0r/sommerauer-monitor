"""Pure decoders for the confirmed core register profile."""

from dataclasses import dataclass
from datetime import timedelta
from typing import Final


PROFILE_ID: Final = "core"
PROFILE_VERSION: Final = "1"
DECODER_VERSION: Final = "1"
SOURCE: Final = "modbus_fc03"


class DecodeError(ValueError):
    """A register block does not satisfy the documented core data contract."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class RegisterBlock:
    offset: int
    count: int
    signal_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DecodedSignal:
    signal_id: str
    value: int
    unit: str
    offset: int
    raw_words: tuple[int, ...]
    profile_id: str = PROFILE_ID
    profile_version: str = PROFILE_VERSION
    decoder_version: str = DECODER_VERSION
    source: str = SOURCE


CORE_PROFILE: Final = (
    RegisterBlock(4102, 1, ("boiler.temperature",)),
    RegisterBlock(28688, 2, ("boiler.operating_minutes",)),
    RegisterBlock(36864, 2, ("buffer.top_temperature", "buffer.bottom_temperature")),
)

_BLOCKS_BY_OFFSET: Final = {block.offset: block for block in CORE_PROFILE}


def signed16(raw: int) -> int:
    """Interpret one unsigned 16-bit word as two's-complement signed16."""
    _validate_word(raw)
    return raw if raw < 0x8000 else raw - 0x10000


def decode_register_block(offset: int, words: tuple[int, ...] | list[int]) -> tuple[DecodedSignal, ...]:
    """Decode exactly one explicitly confirmed FC03 block; never infer other channels."""
    block = _BLOCKS_BY_OFFSET.get(offset)
    if block is None:
        raise DecodeError("unknown_register_block", f"Offset {offset} is not in the core profile")

    raw_words = tuple(words)
    if len(raw_words) != block.count:
        raise DecodeError(
            "invalid_word_count",
            f"Offset {offset} requires {block.count} words, got {len(raw_words)}",
        )
    for word in raw_words:
        try:
            _validate_word(word)
        except ValueError as exc:
            raise DecodeError("invalid_register_word", str(exc)) from exc

    if offset == 4102:
        temperature = signed16(raw_words[0])
        value = _validated_temperature(temperature)
        return (_signal(block, block.signal_ids[0], value, "°C", raw_words),)

    if offset == 28688:
        days, remaining_minutes = raw_words
        if remaining_minutes >= 1440:
            raise DecodeError(
                "invalid_counter",
                f"Remaining minutes must be in 0..1439, got {remaining_minutes}",
            )
        total_minutes = days * 1440 + remaining_minutes
        return (_signal(block, block.signal_ids[0], total_minutes, "min", raw_words),)

    temperatures = tuple(_validated_temperature(signed16(word)) for word in raw_words)
    return tuple(
        _signal(block, signal_id, value, "°C", raw_words)
        for signal_id, value in zip(block.signal_ids, temperatures, strict=True)
    )


def validate_operating_counter_progression(
    previous_minutes: int,
    current_minutes: int,
    elapsed: timedelta,
) -> None:
    """Reject counter rollback or growth beyond elapsed wall time plus minute quantization.

    One additional minute is allowed for the unknown phase of the device's minute
    boundary. This does not infer a counter reset/rollover policy or heating duty cycle.
    """
    if elapsed < timedelta(0):
        raise DecodeError("invalid_counter_time", "Elapsed time cannot be negative")
    if previous_minutes < 0 or current_minutes < 0:
        raise DecodeError("invalid_counter", "Operating minutes cannot be negative")
    if current_minutes < previous_minutes:
        raise DecodeError("invalid_counter_regression", "Operating counter moved backwards")

    elapsed_whole_minutes = elapsed // timedelta(minutes=1)
    maximum_increase = elapsed_whole_minutes + 1
    if current_minutes - previous_minutes > maximum_increase:
        raise DecodeError(
            "implausible_counter_increase",
            "Operating counter increased faster than elapsed time permits",
        )


def _validated_temperature(value: int) -> int:
    if value == 110 or not -5 < value < 110:
        raise DecodeError("invalid_temperature", f"Core temperature out of range: {value} °C")
    return value


def _signal(
    block: RegisterBlock,
    signal_id: str,
    value: int,
    unit: str,
    raw_words: tuple[int, ...],
) -> DecodedSignal:
    return DecodedSignal(signal_id, value, unit, block.offset, raw_words)


def _validate_word(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFFFF:
        raise ValueError(f"Register word must be an integer in 0..65535, got {value!r}")
