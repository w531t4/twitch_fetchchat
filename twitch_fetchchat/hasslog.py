# Copyright (c) 2025 w531t4
#
# This file is licensed under the MIT License.
# See the LICENSE file in the project root for full license text.

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
