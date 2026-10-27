"""Live diagnostic view and recording of the selected game window (Windows)."""
import sys
import os
import shutil
import tempfile
import time
from pathlib import Path
from datetime import datetime
from uuid import uuid4
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageDraw, ImageTk
from app import windows, capture_client
from vision import progress_percent, obstacle_ahead


class Viewer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('GD Trainer — просмотр и запись')
        self.geometry('1000x720')
        self.configure(bg='#111827')
        self.items = []
        self.running = False
        self.writer = None
        self.record_size = None
        self.last_write = 0
        self.record_path = None
        self.temp_path = None
        self.record_frames = 0
        self.record_hotkey_down = False
        self.refresh_hotkey_down = False
        header = tk.Frame(self, bg='#111827', padx=18, pady=12)
        header.pack(fill='x')
        tk.Label(header, text='GD VIEWER', font=('Segoe UI', 18, 'bold'), bg='#111827', fg='#f8fafc').pack(anchor='w')
        tk.Label(header, text='Просмотр игры и запись попыток', font=('Segoe UI', 10), bg='#111827', fg='#a5b4cc').pack(anchor='w')
        top = tk.Frame(self, bg='#111827', padx=18)
        top.pack(fill='x')
        self.choose = ttk.Combobox(top, state='readonly', width=45)
        self.choose.pack(side='left', fill='x', expand=True, ipady=5)
        def button(label, action, colour):
            tk.Button(top, text=label, command=action, bg=colour, fg='white',
                      activebackground='#475569', activeforeground='white', relief='flat',
                      padx=10, pady=6, font=('Segoe UI', 9, 'bold')).pack(side='left', padx=(6, 0))
        button('Обновить  X', self.refresh, '#334155')
        button('Просмотр', self.start, '#2563eb')
        button('Записать', self.record, '#b91c1c')
        button('Стоп', self.stop_record, '#334155')
        button('Папка', self.open_folder, '#334155')
        tk.Label(self, text='Z — начать / остановить запись     X — обновить окна     Игра должна быть видна на экране',
                 bg='#111827', fg='#cbd5e1', font=('Segoe UI', 10), pady=10).pack(fill='x')
        self.label = tk.Label(self, bg='#080d17', fg='white', text='Выберите окно игры и нажмите «Просмотр».')
        self.label.pack(fill='both', expand=True, padx=18, pady=4)
        self.status = tk.StringVar(value='Выберите окно и включите просмотр.')
        tk.Label(self, textvariable=self.status, bg='#111827', fg='#d1d5db', anchor='w', padx=18, pady=5).pack(fill='x')
        self.message = tk.StringVar(value='Видео по клавише Z сохраняется в Videos/GDTrainer.')
        tk.Label(self, textvariable=self.message, bg='#111827', fg='#93c5fd', anchor='w', padx=18, pady=5).pack(fill='x')
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.refresh()
        self.after(50, self.check_hotkey)
        if sys.platform != 'win32':
            self.status.set('Захват окна доступен только в Windows.')

    def open_folder(self):
        try:
            folder = Path.home() / 'Videos' / 'GDTrainer'
            folder.mkdir(parents=True, exist_ok=True)
            os.startfile(folder)
        except (OSError, AttributeError) as exc:
            messagebox.showerror('Папка', str(exc))

    def refresh(self):
        previous = self.choose.current()
        selected = self.items[previous][0] if 0 <= previous < len(self.items) else None
        self.items = windows()
        self.choose['values'] = [f'{title} (окно {hwnd})' for hwnd, title in self.items]
        matches = [i for i, (_, title) in enumerate(self.items) if 'geometry dash' in title.lower()]
        old = next((i for i, (hwnd, _) in enumerate(self.items) if hwnd == selected), None)
        if old is not None:
            self.choose.current(old)
        elif matches:
            self.choose.current(matches[0])
        elif self.items:
            self.choose.current(0)

    def start(self):
        i = self.choose.current()
        if self.writer is not None:
            messagebox.showerror('Просмотр', 'Сначала остановите запись.')
            return
        if i < 0:
            messagebox.showerror('Окно', 'Выберите окно игры.')
            return
        self.hwnd = self.items[i][0]
        if not self.running:
            self.running = True
            self.tick()

    def check_hotkey(self):
        if sys.platform == 'win32':
            import ctypes
            get_key = ctypes.windll.user32.GetAsyncKeyState
            f8 = bool(get_key(0x77) & 0x8000)
            combo = all(get_key(key) & 0x8000 for key in (0x11, 0x10, 0x52))  # Ctrl+Shift+R
            z_key = bool(get_key(0x5A) & 0x8000)
            x_key = bool(get_key(0x58) & 0x8000)
            foreground = ctypes.windll.user32.GetForegroundWindow
            foreground.restype = ctypes.c_void_p
            active = foreground()
            root = ctypes.windll.user32.GetAncestor
            root.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            root.restype = ctypes.c_void_p
            viewer_root = root(self.winfo_id(), 2)
            allowed = active in (viewer_root, getattr(self, 'hwnd', None))
            down = f8 or combo or z_key
            if x_key and not self.refresh_hotkey_down and allowed:
                self.refresh()
                self.message.set('Список окон обновлён. Для другого окна выберите его и нажмите «Просмотр».')
            self.refresh_hotkey_down = x_key
            if down and not self.record_hotkey_down and self.running and allowed:
                if self.writer is not None:
                    self.stop_record()
                else:
                    folder = Path.home() / 'Videos' / 'GDTrainer'
                    try:
                        folder.mkdir(parents=True, exist_ok=True)
                        name = datetime.now().strftime('GD_%Y%m%d_%H%M%S_') + uuid4().hex[:6] + '.mp4'
                        self.record(str(folder / name))
                    except OSError as exc:
                        self.status.set('Не удалось создать папку видео: ' + str(exc))
            self.record_hotkey_down = down
        self.after(50, self.check_hotkey)

    def record(self, path=None):
        if not self.running:
            messagebox.showerror('Запись', 'Сначала включите просмотр.')
            return
        if self.writer is not None:
            return
        try:
            import cv2
        except ImportError:
            messagebox.showerror('Запись', 'Установите библиотеку: py -3.12 -m pip install opencv-python')
            return
        if path is None:
            path = filedialog.asksaveasfilename(defaultextension='.mp4', filetypes=[('MP4 video', '*.mp4')])
        if not path:
            return
        try:
            frame = capture_client(self.hwnd)
            w, h = frame.size
            # Codec dimensions should be even.
            size = (w - w % 2, h - h % 2)
            if w < 300 or h < 150:
                raise RuntimeError('Окно игры слишком маленькое или свёрнуто. Разверните его и повторите.')
            # OpenCV on Windows can fail when a filename contains non-ASCII
            # characters. Write to a temporary file, then move with Python.
            handle, temp_path = tempfile.mkstemp(prefix='gd_record_', suffix='.mp4')
            os.close(handle)
            codec_path = temp_path
            if sys.platform == 'win32':
                import ctypes
                kernel = ctypes.windll.kernel32
                buf = ctypes.create_unicode_buffer(32768)
                if kernel.GetShortPathNameW(temp_path, buf, len(buf)):
                    codec_path = buf.value
            writer = cv2.VideoWriter(codec_path, cv2.VideoWriter_fourcc(*'mp4v'), 10, size)
            if not writer.isOpened():
                writer.release()
                os.unlink(temp_path)
                raise RuntimeError('Не удалось запустить MP4-кодировщик. Проверьте установку OpenCV и доступ к временной папке.')
            self.writer, self.record_size, self.record_path = writer, size, path
            self.temp_path = temp_path
            self.record_frames = 0
            self.last_write = 0
            self.message.set('Идёт запись. Нажмите Z, чтобы сохранить видео.')
        except Exception as exc:
            messagebox.showerror('Запись', str(exc))

    def stop_record(self):
        if self.writer is not None:
            self.writer.release()
            self.writer = None
            try:
                if self.record_frames == 0:
                    os.unlink(self.temp_path)
                    raise RuntimeError('Нет кадров: убедитесь, что игра развёрнута и видна в просмотре.')
                shutil.move(self.temp_path, self.record_path)
                self.message.set(f'Сохранено: {self.record_path} ({self.record_frames} кадров)')
            except (OSError, RuntimeError) as exc:
                messagebox.showerror('Запись', f'{exc}\nВременный файл: {self.temp_path}')
                self.status.set('Не удалось сохранить запись.')

    def tick(self):
        if not self.running:
            return
        try:
            frame = capture_client(self.hwnd).convert('RGB')
            pct = progress_percent(frame)
            obstacle = obstacle_ahead(frame)
            w, h = frame.size
            draw = ImageDraw.Draw(frame)
            draw.rectangle((int(w*.42), int(h*.62), int(w*.54), int(h*.715)), outline='red' if obstacle else 'yellow', width=3)
            draw.rectangle((int(w*.322), int(h*.012), int(w*.678), int(h*.035)), outline='cyan', width=2)
            text = f'Progress: {pct:.1f}%' if pct is not None else 'Progress: not detected'
            text += ' | obstacle: YES' if obstacle else ' | obstacle: no'
            draw.rectangle((0, h-30, min(w, 450), h), fill='black')
            draw.text((5, h-25), text, fill='white')
            if self.writer is not None and time.monotonic() - self.last_write >= .1:
                import cv2
                import numpy as np
                self.writer.write(cv2.cvtColor(np.array(frame.resize(self.record_size)), cv2.COLOR_RGB2BGR))
                self.last_write = time.monotonic()
                self.record_frames += 1
            display = frame.copy()
            display.thumbnail((max(1, self.label.winfo_width()), max(1, self.label.winfo_height())), Image.Resampling.LANCZOS)
            self.photo = ImageTk.PhotoImage(display)
            self.label.configure(image=self.photo, text='')
            self.status.set(('Запись: ' + self.record_path if self.writer is not None else 'Просмотр (Z: запись)') + ' | ' + text)
        except Exception as exc:
            self.running = False
            self.stop_record()
            self.status.set('Ошибка захвата: ' + str(exc))
            return
        self.after(100, self.tick)

    def close(self):
        self.running = False
        self.stop_record()
        self.destroy()


if __name__ == '__main__':
    Viewer().mainloop()
