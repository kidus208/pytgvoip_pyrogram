# PytgVoIP-Pyrogram - Pyrogram support module for Telegram VoIP Library for Python
# Copyright (C) 2020 bakatrouble <https://github.com/bakatrouble>
#
# This file is part of PytgVoIP.
#
# PytgVoIP is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# PytgVoIP is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with PytgVoIP.  If not, see <http://www.gnu.org/licenses/>.

import asyncio
import os
from collections import deque
from typing import Union, List, IO

from tgvoip_pyrogram import VoIPOutgoingCall, VoIPIncomingCall, VoIPService
from tgvoip_pyrogram.base_call import VoIPCallBase

class VoIPFileStreamCallMixin(VoIPCallBase):
    def __init__(self, *args, **kwargs):
        super(VoIPFileStreamCallMixin, self).__init__(*args, **kwargs)
        self.input_files = deque()
        self.hold_files = deque()
        self.current_file_index = 0
        self.last_file_name = None
        self.current_file = None
        self.current_bytes_offset = 0
        self.force_seek = False
        self.output_file = None
        self.ctrl.set_send_audio_frame_callback(self._read_frame)
        self.ctrl.set_recv_audio_frame_callback(self._write_frame)
        self.file_changed_handlers = []
        self.file_progress_handlers = []
        self.last_progress_percentage = 0
        self.event_loop = asyncio.get_event_loop()

    def __del__(self):
        self.clear_play_queue()
        self.clear_hold_queue()
        self.unset_output_file()

    def play(self, f: Union[IO, str]):
        if isinstance(f, str):
            f = open(f, 'rb')
        elif not hasattr(f, 'mode') or 'b' not in f.mode or not any(m in f.mode for m in 'rxa+'):
            print('file must be opened in binary reading/updating mode')
            return
        self.input_files.append(f)

    def play_on_hold(self, files: List[Union[IO, str]]):
        if not isinstance(files, (list, tuple, set)):
            print('list, tuple or set expected, got {}'.format(type(files)))
            return
        self.clear_hold_queue()
        for f in files:
            if isinstance(f, str):
                f = open(f, 'rb')
            elif not hasattr(f, 'mode') or 'b' not in f.mode or not any(m in f.mode for m in 'rxa+'):
                print('file must be opened in binary reading/updating mode')
                continue
            self.hold_files.append(f)

    def set_output_file(self, f: Union[IO, str]):
        if isinstance(f, str):
            f = open(f, 'wb')
        elif 'b' not in f.mode or not any(m in f.mode for m in 'wxa+'):
            print('file must be opened in binary writing/updating mode')
            return
        self.output_file = f

    def clear_play_queue(self):
        for f in self.input_files:
            f.close()
        self.input_files.clear()
        self.clear_file_info()

    def clear_hold_queue(self):
        for f in self.hold_files:
            f.close()
        self.hold_files.clear()
        self.clear_file_info()

    def clear_file_info(self):
        self.last_file_name = None
        self.current_file = None
        self.current_file_index = 0
        self.current_bytes_offset = 0

    def unset_output_file(self):
        if self.output_file:
            self.output_file.close()
        self.output_file = None

    def _read_frame(self, length: int) -> bytes:
        frame = b''
        file_index = self.current_file_index
        files = self.hold_files if len(self.hold_files) else self.input_files

        if file_index >= len(files):
            print('file index unnexistent')
            return
        self.current_file = file = files[file_index]
        if self.force_seek:
            file.seek(self.current_bytes_offset)
            self.force_seek = False
        frame = file.read(length)
        self.current_bytes_offset = file.tell()

        if not hasattr(file, 'size'):
            file.size = os.path.getsize(file.name)

        if self.last_file_name != file.name:
            self.file_changed()
            self.last_file_name = file.name
        self.file_progress(self.current_bytes_offset, file.size, (self.current_bytes_offset*100)/file.size)

        if len(frame) != length:
            self.next_file()
        return frame

    def _write_frame(self, frame: bytes) -> None:
        if self.output_file:
            self.output_file.write(frame)

    def on_file_changed(self, func: callable) -> callable: # the current file on self.hold_files has changed
        self.file_changed_handlers.append(func)
        return func

    def on_file_progress(self, func: callable) -> callable: # when a frame is sent
        self.file_progress_handlers.append(func)
        return func

    def file_changed(self):
        args = (self, self.current_file, self.current_file_index)
        for handler in self.file_changed_handlers:
            asyncio.iscoroutinefunction(handler) and asyncio.run_coroutine_threadsafe(handler(*args), self.event_loop)

    def file_progress(self, bytes_offset: int, total_bytes: int, percentage: int):
        if self.last_progress_percentage == round(percentage, 1):
            return
        args = (self, bytes_offset, total_bytes, percentage)
        self.last_progress_percentage = round(percentage, 1)
        for handler in self.file_progress_handlers:
            asyncio.iscoroutinefunction(handler) and asyncio.run_coroutine_threadsafe(handler(*args), self.event_loop)

    def previous_file(self):
        if len(self.input_files):
            print('previous_file can only be used with play_on_hold')
            return
        file_index = self.current_file_index
        file = self.hold_files[file_index]
        file.seek(0)
        self.current_bytes_offset = 0
        self.current_file_index = file_index-1 if file_index-1 >= 0 else len(self.hold_files)-1
        self.current_file = self.hold_files[self.current_file_index]
        return self.current_file

    def next_file(self):
        file_index = self.current_file_index
        if len(self.input_files):
            file = self.input_files[file_index]
            file.close()
            self.input_files.popleft()
            self.current_file = self.input_files[self.current_file_index]
        elif len(self.hold_files):
            file = self.hold_files[file_index]
            file.seek(0)
            self.current_bytes_offset = 0
            self.current_file_index = file_index+1 if file_index+1 < len(self.hold_files) else 0
            self.current_file = self.hold_files[self.current_file_index]
            return self.current_file

    def seek(self, bytes_offset: int, file_index: int = None):
        # round to the largest even number lower than or equal to bytes_offset
        even,rest = divmod(bytes_offset, 2)
        bytes_offset = even*2

        files = self.hold_files if len(self.hold_files) else self.input_files
        if file_index >= len(files):
            print('file index unnexistent')
            return
        if file_index != None:
            self.current_file_index = file_index
            self.current_file = files[file_index]
        self.current_bytes_offset = bytes_offset
        self.force_seek = True

class VoIPOutgoingFileStreamCall(VoIPFileStreamCallMixin, VoIPOutgoingCall):
    pass


class VoIPIncomingFileStreamCall(VoIPFileStreamCallMixin, VoIPIncomingCall):
    pass


class VoIPFileStreamService(VoIPService):
    incoming_call_class = VoIPIncomingFileStreamCall
    outgoing_call_class = VoIPOutgoingFileStreamCall
