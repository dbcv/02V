import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import mido
import time
import threading
import json
import os
from window.voiceIndex import VoiceIndexWindow

# UIの設定
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

VOICE_FILE = "voice.json"



class ELS02SysExApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("ELS-02 SysEx Manager Pro")
        self.geometry("800x550")

        self.active_param_editor = None
        self.inport = None
        self.outport = None
        self.last_sysex = None
        self.voice_db = {}
        self.load_voice_json()

        self.setup_gui()

    def load_voice_json(self):
        if os.path.exists(VOICE_FILE):
            with open(VOICE_FILE, 'r') as f:
                raw_db = json.load(f)
                # 旧形式から新形式へのコンバーター
                for k, v in raw_db.items():
                    if isinstance(v, list):
                        self.voice_db[k] = {"voice": v, "param": []}
                    else:
                        self.voice_db[k] = v
        else:
            self.save_voice_json()       

    def save_voice_json(self):
        with open(VOICE_FILE, 'w') as f:
            json.dump(self.voice_db, f, indent=4, ensure_ascii=False)

    def setup_gui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.sidebar = ctk.CTkFrame(self, width=200)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        
        ctk.CTkLabel(self.sidebar, text="ELS-02 Control", font=("bold", 16)).pack(pady=20)
        
        self.in_combo = ctk.CTkComboBox(self.sidebar, values=mido.get_input_names(), command=self.change_inport)
        self.in_combo.pack(pady=10, padx=10)
        
        self.out_combo = ctk.CTkComboBox(self.sidebar, values=mido.get_output_names(), command=self.change_outport)
        self.out_combo.pack(pady=10, padx=10)

        # 音色インデックスボタン
        self.btn_index = ctk.CTkButton(self.sidebar, text="音色インデックス", fg_color="purple", command=self.open_voice_index)
        self.btn_index.pack(pady=30, padx=10)

        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
        self.log_box = ctk.CTkTextbox(self.main_frame)
        self.log_box.pack(fill="both", expand=True, padx=10, pady=10)

    def log(self, msg):
        self.log_box.insert("end", f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        self.log_box.see("end")

    def change_inport(self, name):
        if self.inport: self.inport.close()
        self.inport = mido.open_input(name, callback=self.midi_callback)

    def change_outport(self, name):
        if self.outport: self.outport.close()
        self.outport = mido.open_output(name)

    def midi_callback(self, msg):
        if msg.type == 'sysex':
            # 16進数文字列リストに変換
            hex_list = [format(b, '02X') for b in msg.data]
            self.last_sysex = msg.data
            
            # パラメータ記録中のエディタがあれば渡す
            if self.active_param_editor and self.active_param_editor.is_recording_param:
                self.active_param_editor.add_param(hex_list)
            
            self.log(f"Received SysEx: {hex_list[:4]}...")

    def send_voice_to_uk1(self, voice_data_hex_list):
        if not self.outport:
            messagebox.showerror("Error", "Output port not connected")
            return
        
        # F0 43 70 78 44 10 [00:UK1] [Data 6byte] F7
        header =       [0x43, 0x70, 0x78, 0x44, 0x10, 0x00]
        data = [int(x, 16) for x in voice_data_hex_list]
        panelsection_data = [0x10, int(voice_data_hex_list[0], 16)]
        msg = mido.Message('sysex', data=header + panelsection_data)
        self.outport.send(msg)
        msg = mido.Message('sysex', data=header + data)
        self.outport.send(msg)
        self.log(f"Sent Voice to UK1: {voice_data_hex_list}")
        
    def send_voice_to_section(self, section_name, voice_entry):
        # voice_entry は {"voice": [...], "param": [[...], [...]]} の形式
        if not self.outport: return
        
        voice_data = voice_entry["voice"]
        params = voice_entry.get("param", [])
        
        # 1. 音色変更（前回修正いただいたロジック）
        sections = {"UK1": 0x00, "UK2": 0x01, "LK1": 0x02, "LK2": 0x03, "PK1": 0x06, "PK2": 0x07}
        mm = sections.get(section_name, 0x00)
        header = [0x43, 0x70, 0x78, 0x44, 0x10, mm]
        
        # パネルセクション切り替え送信
        panel_msg = mido.Message('sysex', data=header + [0x10, int(voice_data[0], 16)])
        self.outport.send(panel_msg)
        
        # ボイスデータ本体送信
        voice_msg = mido.Message('sysex', data=header + [int(x, 16) for x in voice_data])
        self.outport.send(voice_msg)
        
        # 2. 記録された追加パラメータを順次送信
        for p_data in params:
            # 記録されたデータ自体が [LL, D1, D2...] の形であることを想定
            # 送信先 mm は現在の選択に合わせる必要があるためヘッダーを再結合
            p_msg = mido.Message('sysex', data=header + [int(x, 16) for x in p_data])
            self.outport.send(p_msg)
            time.sleep(0.005) # 連続送信による楽器側の処理落ち防止
            
        self.log(f"Sent {section_name} with {len(params)} params.")

    def open_voice_index(self):
        VoiceIndexWindow(self)

if __name__ == "__main__":
    app = ELS02SysExApp()
    app.mainloop()