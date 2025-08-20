# Copyright (c) 2025 w531t4
#
# This file is licensed under the MIT License.
# See the LICENSE file in the project root for full license text.


class _TransportBase:
    def send(self, lines):
        raise NotImplementedError
