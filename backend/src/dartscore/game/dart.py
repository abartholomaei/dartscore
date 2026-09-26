"""A single dart as the game logic sees it."""

from dataclasses import dataclass

BULL = 25
MISS_SEGMENT = 0


@dataclass(frozen=True)
class Dart:
    """segment 0 = miss, 25 = bull; multiplier 1-3 (bull: 1 = 25, 2 = 50)."""

    segment: int
    multiplier: int

    def __post_init__(self) -> None:
        valid_segment = self.segment in range(21) or self.segment == BULL
        if not valid_segment:
            raise ValueError(f"Invalid segment {self.segment}")
        if self.segment == MISS_SEGMENT:
            if self.multiplier not in (0, 1):
                raise ValueError("A miss has multiplier 0")
        elif self.multiplier not in (1, 2, 3) or (self.segment == BULL and self.multiplier == 3):
            raise ValueError(f"Invalid multiplier {self.multiplier} for segment {self.segment}")

    @classmethod
    def miss(cls) -> "Dart":
        return cls(MISS_SEGMENT, 0)

    @classmethod
    def parse(cls, label: str) -> "Dart":
        """'T20', 'D16', 'S5', '5', '25', 'BULL', 'MISS'."""
        text = label.strip().upper()
        if text in ("MISS", "M", "0"):
            return cls.miss()
        if text in ("BULL", "DB", "D25", "50"):
            return cls(BULL, 2)
        if text in ("25", "SB", "S25", "OB"):
            return cls(BULL, 1)
        prefix = {"S": 1, "D": 2, "T": 3}
        if text[0] in prefix:
            return cls(int(text[1:]), prefix[text[0]])
        return cls(int(text), 1)

    @property
    def points(self) -> int:
        return self.segment * self.multiplier

    @property
    def is_miss(self) -> bool:
        return self.segment == MISS_SEGMENT

    @property
    def is_double(self) -> bool:
        return self.multiplier == 2

    @property
    def is_triple(self) -> bool:
        return self.multiplier == 3

    @property
    def label(self) -> str:
        if self.segment == MISS_SEGMENT:
            return "MISS"
        if self.segment == BULL:
            return "BULL" if self.multiplier == 2 else "25"
        return f"{'SDT'[self.multiplier - 1]}{self.segment}"

    def __str__(self) -> str:
        return self.label
