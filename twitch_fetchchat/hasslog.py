# SPDX-FileCopyrightText: 2025 Aaron White <w531t4@gmail.com>
# SPDX-License-Identifier: MIT

from typing import Protocol, Literal, overload

Level = Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"]

class HassLog(Protocol):
    """ helper for communicating structure for hass log function """
    @overload
    def __call__(self, message: str, /) -> None: ...
    @overload
    def __call__(self, message: str, /, level: Level) -> None: ...
    @overload
    def __call__(self, message: str, /, *, level: Level) -> None: ...
    def __call__(self, message: str, /, *args, **kwargs) -> None: ...
