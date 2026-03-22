from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EpisodeState:
    characters: dict[str, dict] = field(default_factory=dict)
    voice_map: dict[str, str] = field(default_factory=dict)
    processed_scenes: list[int] = field(default_factory=list)

    def remember_character(self, speaker: str, voice: str, profile: dict) -> None:
        sp = (speaker or "unknown_1").strip().lower()
        if sp not in self.characters:
            self.characters[sp] = {
                "speaker": sp,
                "voice": voice,
                "profile": dict(profile),
            }
        self.voice_map[sp] = voice

