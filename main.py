import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import mido
import time
import threading
import json
import os

# UIの設定
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

VOICE_FILE = "voice.json"

class VoiceIndexWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Voice Index")
        self.geometry("400x600")
        self.attributes('-topmost', True) # 常に最前面

        self.setup_gui()
        self.refresh_buttons()

    def setup_gui(self):
        self.label = ctk.CTkLabel(self, text="Voice Library", font=ctk.CTkFont(size=18, weight="bold"))
        self.label.pack(pady=10)

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
        
        for name, data in self.parent.voice_db.items():
            btn = ctk.CTkButton(self.scroll_frame, text=name, 
                               command=lambda d=data: self.parent.send_voice_to_uk1(d))
            btn.pack(pady=5, padx=10, fill="x")

class ELS02SysExApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("ELS-02 SysEx Manager Pro")
        self.geometry("800x550")

        self.inport = None
        self.outport = None
        self.last_sysex = None
        self.voice_db = {}
        self.load_voice_json()

        self.setup_gui()

    def load_voice_json(self):
        if os.path.exists(VOICE_FILE):
            with open(VOICE_FILE, 'r') as f:
                self.voice_db = json.load(f)
        else:
            self.save_voice_json()

    def save_voice_json(self):
        with open(VOICE_FILE, 'w') as f:
            json.dump(self.voice_db, f, indent=4)

    def setup_gui(self):
        # ... (前回のサイドバー設定は維持)
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
            self.last_sysex = msg.data # midoのdataはF0/F7を含まない本体のみ
            # 受信確認用に全データをログ
            self.log(f"Received SysEx (Len:{len(msg.hex())})")

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
        
    def send_voice_to_section(self, section_name, voice_data_hex_list):
        if not self.outport:
            messagebox.showerror("Error", "Output port not connected")
            return
        
        # セクション名とAddress(mm)の対応
        sections = {
            "UK1": 0x00, "UK2": 0x01,
            "LK1": 0x02, "LK2": 0x03,
            "PK1": 0x06, "PK2": 0x07,
            "Lead1": 0x04, "Lead2": 0x05
        }
        mm = sections.get(section_name, 0x00)

        # ヘッダー構成 (F0 43 70 78 44 10まで)
        header = [0x43, 0x70, 0x78, 0x44, 0x10, mm]
        
        # 1. ボイスパネルセクションの切り替え (ご提示の修正)
        # 10 08 (Voice Assign) の前にセクションの状態を確定させる
        panelsection_data = [0x10, int(voice_data_hex_list[0], 16)]
        msg_panel = mido.Message('sysex', data=header + panelsection_data)
        self.outport.send(msg_panel)
        
        # 2. 実際のボイスデータ送信 (6byte: LL + Data 5byte)
        data = [int(x, 16) for x in voice_data_hex_list]
        msg_voice = mido.Message('sysex', data=header + data)
        self.outport.send(msg_voice)
        
        self.log(f"Sent Voice to {section_name}: {voice_data_hex_list}")

    def open_voice_index(self):
        VoiceIndexWindow(self)

if __name__ == "__main__":
    app = ELS02SysExApp()
    app.mainloop()