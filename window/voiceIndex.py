import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import mido
import time
import threading
import json
import os
import pyaudio
import wave
import datetime
from mido import MidiFile
from window.voiceEdit import VoiceEditWindow

class VoiceIndexWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.save_voice_json = parent.save_voice_json
        self.title("Voice Index")
        self.geometry("800x700") # ラジオボタン分、少し高さを広げました
        self.target_section = tk.StringVar(value="UK1")
        self.attributes('-topmost', True) # 常に最前面

        self.setup_gui()
        self.refresh_buttons()

    def setup_gui(self):
        self.label = ctk.CTkLabel(self, text="Voice Library", font=ctk.CTkFont(size=18, weight="bold"))
        self.label.pack(pady=10)

        # --- 送信先選択セクター (2段 x 4列) ---
        target_frame = ctk.CTkFrame(self)
        target_frame.pack(pady=10, padx=20, fill="x")
        
        ctk.CTkLabel(target_frame, text="Target Section:", font=("bold", 12)).grid(row=0, column=0, columnspan=4, pady=5)

        # セクションの定義
        sections_layout = [
            ["UK1", "UK2", "Lead1", "Lead2"],
            ["LK1", "LK2", "PK1", "PK2"]
        ]

        for r, row_items in enumerate(sections_layout):
            for c, sec in enumerate(row_items):
                rb = ctk.CTkRadioButton(
                    target_frame, 
                    text=sec, 
                    variable=self.target_section, 
                    value=sec,
                    width=80
                )
                rb.grid(row=r+1, column=c, padx=15, pady=5, sticky="w")

        self.btn_add = ctk.CTkButton(self, text="+ Add New Voice (Wait SysEx)", fg_color="orange", hover_color="#CC8400", command=self.wait_for_voice)
        self.btn_add.pack(pady=10, padx=20, fill="x")

        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="Registered Voices")
        self.scroll_frame.pack(pady=10, padx=10, fill="both", expand=True)

    def wait_for_voice(self):
        self.btn_add.configure(text="Waiting for SysEx...", state="disabled")
        self.parent.log("Voice Index: Waiting for SysEx from ELS-02...")
        
        # 記録モードを一時的に強制ONにし、次のSysExを待つスレッドを開始
        threading.Thread(target=self._capture_thread, daemon=True).start()

    def _capture_thread(self):
        captured_data = None
        self.parent.last_sysex = None
        # midoのポートから直接1つメッセージを待つか、親のコールバックを利用
        # ここではシンプルに、親が受信した最新のデータをチェックする方式
        start_wait = time.time()
        while time.time() - start_wait < 10: # 10秒タイムアウト
            if self.parent.last_sysex:
                raw_data = self.parent.last_sysex
                print(raw_data[3], len(raw_data), raw_data[3] == 0x44)
                if len(raw_data) >= 12 and raw_data[3] == 0x44:
                    captured_data = raw_data[6:12]
                    self.parent.last_sysex = None
                    break
            time.sleep(0.1)

        if captured_data:
            self.after(0, lambda: self.ask_voice_name(captured_data))
        else:
            self.parent.log("Voice Index: Timeout or Invalid SysEx.")
        
        self.after(0, lambda: self.btn_add.configure(text="+ Add New Voice (Wait SysEx)", state="normal"))

    def ask_voice_name(self, data):
        dialog = ctk.CTkInputDialog(text="Enter Voice Name:", title="New Voice")
        name = dialog.get_input()
        if name:
            hex_data = [format(b, '02X') for b in data]
            self.parent.voice_db[name] = hex_data
            self.parent.save_voice_json()
            self.refresh_buttons()
            self.parent.log(f"Added: {name} ({hex_data})")

    def refresh_buttons(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        
        self.scroll_frame.grid_columnconfigure((0, 1, 2), weight=1)

        for i, (name, data) in enumerate(self.parent.voice_db.items()):
            item_frame = ctk.CTkFrame(self.scroll_frame, width=200, height=100)
            item_frame.grid(row=i // 3, column=i % 3, padx=10, pady=10)
            item_frame.grid_propagate(False)

            # 再生ボタン: 現在選択されている self.target_section.get() を使用
            play_btn = ctk.CTkButton(
                item_frame, 
                text=name, 
                width=180, 
                height=60,
                fg_color="#2c3e50",
                hover_color="#34495e",
                command=lambda d=data: self.parent.send_voice_to_section(self.target_section.get(), d)
            )
            play_btn.pack(pady=(5, 2), padx=10)

            edit_btn = ctk.CTkButton(
                item_frame, 
                text="Edit", 
                width=180, 
                height=20, 
                fg_color="gray",
                hover_color="#555555",
                font=ctk.CTkFont(size=10),
                command=lambda n=name: self.open_edit_dialog(n)
            )
            edit_btn.pack(pady=(0, 5), padx=10)

    def open_edit_dialog(self, name):
        VoiceEditWindow(self.parent, name)