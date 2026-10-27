"""A small, human-scored evolutionary trainer for Geometry Dash (Windows)."""
import json
import os
import random
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from pathlib import Path
from vision import progress_percent, obstacle_ahead

if sys.platform == 'win32':
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_size_t]

DATA = Path(os.getenv('LOCALAPPDATA', str(Path.home()))) / 'GDTrainer' / 'profiles.json'


def windows():
    if sys.platform != 'win32':
        return []
    found = []
    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                found.append((hwnd, buf.value))
        return True
    user32.EnumWindows(callback(visit), 0)
    return found


def mutate(best, duration):
    """Change a few timings while retaining the best known sequence."""
    if best is None:
        return sorted(random.uniform(.2, duration) for _ in range(max(1, int(duration / 1.5))))
    candidate = list(best)
    for _ in range(random.randint(1, 4)):
        action = random.choice(('move', 'add', 'remove'))
        if action == 'move' and candidate:
            i = random.randrange(len(candidate))
            candidate[i] = max(.1, min(duration, candidate[i] + random.gauss(0, .25)))
        elif action == 'add':
            candidate.append(random.uniform(.1, duration))
        elif action == 'remove' and len(candidate) > 1:
            candidate.pop(random.randrange(len(candidate)))
    return sorted(candidate)


def capture_client(hwnd):
    from PIL import ImageGrab
    if not user32.IsWindow(hwnd) or user32.IsIconic(hwnd):
        raise RuntimeError('Окно игры закрыто или свёрнуто. Разверните его для захвата.')
    rect = wintypes.RECT()
    point = wintypes.POINT(0, 0)
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)) or not user32.ClientToScreen(hwnd, ctypes.byref(point)):
        raise RuntimeError('Не удалось определить область окна игры.')
    return ImageGrab.grab(bbox=(point.x, point.y, point.x + rect.right, point.y + rect.bottom), all_screens=True)


def play(hwnd, sequence, duration, cancelled, reactive, resume):
    if not user32.IsWindow(hwnd) or not user32.SetForegroundWindow(hwnd):
        raise RuntimeError('Не удалось активировать выбранное окно. Откройте игру и выберите её заново.')
    time.sleep(.3)
    if user32.GetForegroundWindow() != hwnd:
        raise RuntimeError('Окно игры не получило фокус. Попробуйте ещё раз.')
    if resume:
        # The game must already be paused; do not send a pause key elsewhere.
        user32.keybd_event(0x20, 0, 0, 0)
        try:
            if cancelled.wait(.05):
                return False, None, False
        finally:
            user32.keybd_event(0x20, 0, 2, 0)
    start = time.monotonic()
    last_jump = start - 1
    next_capture = start
    peak = None
    index = 0
    while time.monotonic() - start < duration:
        if cancelled.wait(.01):
            return False, None, False
        if user32.GetForegroundWindow() != hwnd:
            raise RuntimeError('Окно игры потеряло фокус; попытка остановлена.')
        now = time.monotonic()
        if now >= next_capture:
            frame = capture_client(hwnd)
            value = progress_percent(frame)
            if value is not None and peak is not None and peak >= 2 and value < peak - 1.5:
                return True, peak, True
            if reactive and now - last_jump > .45 and obstacle_ahead(frame):
                user32.keybd_event(0x20, 0, 0, 0)
                try:
                    if cancelled.wait(.05):
                        return False, None, False
                finally:
                    user32.keybd_event(0x20, 0, 2, 0)
                last_jump = time.monotonic()
            next_capture = time.monotonic() + .03
            if value is not None:
                peak = max(peak or 0, value)
        while not reactive and index < len(sequence) and time.monotonic() - start >= sequence[index]:
            user32.keybd_event(0x20, 0, 0, 0)
            try:
                if cancelled.wait(.05):
                    return False, None, False
            finally:
                user32.keybd_event(0x20, 0, 2, 0)
            index += 1
    return True, peak, False


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('GD Trainer')
        self.geometry('650x480')
        self.resizable(False, False)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.cancelled = threading.Event()
        self.running = False
        self.candidate = None
        self.attempt_profile = None
        self.window_list = []
        try:
            self.profiles = json.loads(DATA.read_text(encoding='utf-8')) if DATA.exists() else {}
            if not isinstance(self.profiles, dict):
                raise ValueError('ожидался словарь профилей')
        except (ValueError, OSError) as exc:
            messagebox.showerror('Ошибка профилей', f'Не удалось прочитать {DATA}: {exc}\nИсправьте файл и запустите программу снова.')
            self.destroy()
            return
        frame = ttk.Frame(self, padding=14)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Окно игры:').grid(row=0, column=0, sticky='w')
        self.window_box = ttk.Combobox(frame, state='readonly', width=53)
        self.window_box.grid(row=1, column=0, sticky='ew')
        ttk.Button(frame, text='Обновить', command=self.refresh).grid(row=1, column=1, padx=6)
        ttk.Label(frame, text='Название уровня / профиль:').grid(row=2, column=0, sticky='w', pady=(10, 0))
        self.level = ttk.Entry(frame)
        self.level.insert(0, 'Уровень 1')
        self.level.grid(row=3, column=0, sticky='ew')
        ttk.Label(frame, text='Длительность попытки, секунд (1–300):').grid(row=4, column=0, sticky='w', pady=(10, 0))
        self.duration = ttk.Entry(frame)
        self.duration.insert(0, '120')
        self.duration.grid(row=5, column=0, sticky='ew')
        self.reactive = tk.BooleanVar(value=True)
        self.resume = tk.BooleanVar(value=True)
        ttk.Checkbutton(frame, text='Реагировать на яркие препятствия (эксперимент)', variable=self.reactive).grid(row=6, column=0, sticky='w')
        ttk.Checkbutton(frame, text='Уровень на паузе: нажать пробел для продолжения', variable=self.resume).grid(row=7, column=0, sticky='w')
        self.run_button = ttk.Button(frame, text='Запустить попытку', command=self.run_attempt)
        self.run_button.grid(row=8, column=0, sticky='w', pady=12)
        ttk.Button(frame, text='Стоп', command=self.cancelled.set).grid(row=8, column=1)
        self.status = tk.StringVar(value='Выберите окно, откройте уровень и запустите попытку.')
        ttk.Label(frame, textvariable=self.status, wraplength=600).grid(row=9, column=0, columnspan=2, sticky='w')
        ttk.Label(frame, text='Бот пробует считать полоску прогресса; после попытки проверьте процент. Перед каждой новой попыткой вручную перезапускайте уровень. Одинаковое название сохраняет обучение для уровня.', wraplength=600).grid(row=10, column=0, columnspan=2, sticky='w', pady=15)
        frame.columnconfigure(0, weight=1)
        self.refresh()
        if sys.platform != 'win32':
            self.status.set('Для управления игрой требуется Windows.')
            self.run_button.state(['disabled'])

    def refresh(self):
        self.window_list = windows()
        self.window_box['values'] = [f'{title} (окно {hwnd})' for hwnd, title in self.window_list]
        matches = [i for i, (_, title) in enumerate(self.window_list) if 'geometry dash' in title.lower()]
        if matches:
            self.window_box.current(matches[0])
        elif self.window_list:
            self.window_box.current(0)

    def run_attempt(self):
        if self.running:
            return
        try:
            index = self.window_box.current()
            if index < 0:
                raise ValueError('Выберите окно игры.')
            duration = float(self.duration.get().replace(',', '.'))
            if not 1 <= duration <= 300:
                raise ValueError('Длительность должна быть от 1 до 300 секунд.')
            name = self.level.get().strip()
            if not name:
                raise ValueError('Введите название уровня.')
        except ValueError as exc:
            messagebox.showerror('Проверьте настройки', str(exc))
            return
        profile = self.profiles.get(name, {})
        reactive, resume = self.reactive.get(), self.resume.get()
        self.candidate = mutate(profile.get('best'), duration)
        self.attempt_profile = (name, duration)
        self.cancelled.clear()
        self.running = True
        self.run_button.state(['disabled'])
        self.status.set('Попытка идёт. Для остановки нажмите «Стоп»; потеря фокуса тоже остановит ввод.')
        hwnd = self.window_list[index][0]
        def worker():
            try:
                completed, observed, restarted = play(hwnd, self.candidate, duration, self.cancelled, reactive, resume)
                error = None
            except Exception as exc:
                completed, observed, restarted, error = False, None, False, str(exc)
            self.after(0, lambda: self.finished(completed, error, observed, restarted, reactive))
        threading.Thread(target=worker, daemon=True).start()

    def finished(self, completed, error, observed, restarted, reactive):
        self.running = False
        self.run_button.state(['!disabled'])
        if error:
            self.status.set(error)
            return
        if not completed:
            self.status.set('Попытка остановлена; результат не сохранён.')
            return
        hint = (f'Оценка по полосе: {observed:.1f}%. ' if observed is not None else 'Полосу не удалось распознать. ')
        if restarted:
            hint += 'Обнаружен вероятный перезапуск. '
        score = simpledialog.askfloat('Результат', hint + 'Проверьте и введите процент из игры (0–100):', initialvalue=round(observed, 1) if observed is not None else None, minvalue=0, maxvalue=100, parent=self)
        if score is None:
            self.status.set('Результат пропущен. Перезапустите уровень для следующей попытки.')
            return
        if reactive:
            self.status.set(f'Результат: {score}%. Режим анализа не сохраняет последовательность прыжков.')
            return
        name, duration = self.attempt_profile
        profile = self.profiles.setdefault(name, {'duration': duration, 'score': -1, 'best': None, 'attempts': 0})
        profile['duration'] = duration
        profile['attempts'] += 1
        if score > profile['score']:
            profile['score'], profile['best'] = score, self.candidate
        try:
            DATA.parent.mkdir(parents=True, exist_ok=True)
            temp = DATA.with_suffix('.tmp')
            temp.write_text(json.dumps(self.profiles, ensure_ascii=False, indent=2), encoding='utf-8')
            temp.replace(DATA)
        except OSError as exc:
            messagebox.showerror('Ошибка сохранения', str(exc))
            return
        self.status.set(f'Попыток: {profile["attempts"]}; лучший результат: {profile["score"]}%. Перезапустите уровень.')

    def close(self):
        self.cancelled.set()
        self.destroy()


if __name__ == '__main__':
    App().mainloop()
