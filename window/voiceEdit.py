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

class VoiceEditWindow(ctk.CTkToplevel):
    def __init__(self, parent, voice_name):
        super().__init__(parent)
        self.parent = parent
        self.voice_name = voice_name
        self.is_recording_param = False
        self.recorded_params = self.parent.voice_db[voice_name].get("param", [])

        self.title(f"Edit: {voice_name}")
        self.geometry("400x450")
        self.attributes('-topmost', True)

        self.setup_gui()

    def setup_gui(self):
        ctk.CTkLabel(self, text=f"Voice: {self.voice_name}", font=("bold", 16)).pack(pady=10)

        # 名前変更セクション
        self.name_entry = ctk.CTkEntry(self, placeholder_text="New Name")
        self.name_entry.insert(0, self.voice_name)
        self.name_entry.pack(pady=5, padx=20, fill="x")

        self.btn_rename = ctk.CTkButton(self, text="Rename", command=self.rename_voice)
        self.btn_rename.pack(pady=5)

        ctk.CTkFrame(self, height=2, corner_radius=0).pack(pady=15, fill="x", padx=10)

        # パラメータ記録セクション
        self.param_label = ctk.CTkLabel(self, text=f"Recorded Params: {len(self.recorded_params)}")
        self.param_label.pack()

        self.btn_rec_param = ctk.CTkButton(self, text="Start Param Record", fg_color="red", command=self.toggle_param_record)
        self.btn_rec_param.pack(pady=10, padx=20, fill="x")

        self.param_list_box = ctk.CTkTextbox(self, height=150)
        self.param_list_box.pack(pady=10, padx=20, fill="both", expand=True)
        self.update_param_list()

        self.btn_save = ctk.CTkButton(self, text="Save & Close", fg_color="green", command=self.destroy)
        self.btn_save.pack(pady=10)

    def rename_voice(self):
        new_name = self.name_entry.get()
        if new_name and new_name != self.voice_name:
            data = self.parent.voice_db.pop(self.voice_name)
            self.parent.voice_db[new_name] = data
            self.voice_name = new_name
            self.parent.save_voice_json()
            self.parent.refresh_buttons()
            self.parent.log(f"Renamed to: {new_name}")

    def toggle_param_record(self):
        if not self.is_recording_param:
            self.is_recording_param = True
            self.recorded_params = [] # 新規記録時はリセット
            self.btn_rec_param.configure(text="Stop & Save Param", fg_color="darkred")
            self.parent.log(f"Recording params for {self.voice_name}...")
            # 親クラスに記録中であることを伝える
            self.parent.active_param_editor = self
        else:
            self.is_recording_param = False
            self.btn_rec_param.configure(text="Start Param Record", fg_color="red")
            # データを保存
            self.recorded_params_filtered = {}
            data = [x[6:] for x in self.recorded_params]
            for item in data:
                if len(item) < 2:
                    continue
                key = item[0]
                self.recorded_params_filtered[key] = item
            
            self.recorded_params_sorted = sorted(self.recorded_params_filtered.values(), key=lambda x: x[0])

            self.parent.voice_db[self.voice_name]["param"] = list(self.recorded_params_sorted)
            self.parent.save_voice_json()
            self.parent.active_param_editor = None
            self.parent.log(f"Saved {len(self.recorded_params)} params.")

    def add_param(self, data_hex_list):
        self.recorded_params.append(data_hex_list)
        self.update_param_list()
        self.param_label.configure(text=f"Recorded Params: {len(self.recorded_params)}")

    def update_param_list(self):
        self.param_list_box.delete("1.0", "end")
        for p in self.recorded_params:
            self.param_list_box.insert("end", f"{' '.join(p)}\n")