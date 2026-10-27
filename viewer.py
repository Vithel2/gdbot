"""Live diagnostic view and recording of the selected game window (Windows)."""
import sys
import time
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
        top = ttk.Frame(self, padding=10)
        top.pack(fill='x')
        self.choose = ttk.Combobox(top, state='readonly', width=55)
        self.choose.pack(side='left', fill='x', expand=True)
        ttk.Button(top, text='Обновить окна', command=self.refresh).pack(side='left', padx=4)
        ttk.Button(top, text='Просмотр', command=self.start).pack(side='left', padx=4)
        ttk.Button(top, text='Запись MP4', command=self.record).pack(side='left', padx=4)
        ttk.Button(top, text='Остановить запись', command=self.stop_record).pack(side='left', padx=4)
        self.label = tk.Label(self, bg='#080d17', fg='white', text='Выберите окно игры и нажмите «Просмотр».')
        self.label.pack(fill='both', expand=True, padx=10, pady=5)
        self.status = tk.StringVar(value='Видео: не записывается')
        tk.Label(self, textvariable=self.status, bg='#111827', fg='#d1d5db', anchor='w', padx=12, pady=8).pack(fill='x')
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.refresh()
        if sys.platform != 'win32':
            self.status.set('Захват окна доступен только в Windows.')

    def refresh(self):
        self.items = windows()
        self.choose['values'] = [f'{title} (окно {hwnd})' for hwnd, title in self.items]
        matches = [i for i, (_, title) in enumerate(self.items) if 'geometry dash' in title.lower()]
        if matches:
            self.choose.current(matches[0])
        elif self.items:
            self.choose.current(0)

    def start(self):
        i = self.choose.current()
        if i < 0:
            messagebox.showerror('Окно', 'Выберите окно игры.')
            return
        self.hwnd = self.items[i][0]
        if not self.running:
            self.running = True
            self.tick()

    def record(self):
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
        path = filedialog.asksaveasfilename(defaultextension='.mp4', filetypes=[('MP4 video', '*.mp4')])
        if not path:
            return
        try:
            frame = capture_client(self.hwnd)
            w, h = frame.size
            # Codec dimensions should be even.
            size = (w - w % 2, h - h % 2)
            writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*'mp4v'), 10, size)
            if not writer.isOpened():
                writer.release()
                raise RuntimeError('Не удалось открыть MP4-кодировщик.')
            self.writer, self.record_size, self.record_path = writer, size, path
            self.last_write = 0
        except Exception as exc:
            messagebox.showerror('Запись', str(exc))

    def stop_record(self):
        if self.writer is not None:
            self.writer.release()
            self.writer = None
            self.status.set('Запись сохранена: ' + self.record_path)

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
            display = frame.copy()
            display.thumbnail((max(1, self.label.winfo_width()), max(1, self.label.winfo_height())), Image.Resampling.LANCZOS)
            self.photo = ImageTk.PhotoImage(display)
            self.label.configure(image=self.photo, text='')
            self.status.set(('Запись: ' + self.record_path if self.writer is not None else 'Просмотр') + ' | ' + text)
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
