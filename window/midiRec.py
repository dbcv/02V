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

class MidiAudioRecordingWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("MIDI to Audio Recording")
        self.geometry("500x400")
        self.attributes('-topmost', True)
        
        self.midi_path = None
        self.is_processing = False
        
        # フォルダ作成
        self.rec_dir = os.path.join(os.getcwd(), "Recording")
        os.makedirs(self.rec_dir, exist_ok=True)
        
        self.setup_gui()

    def setup_gui(self):
        ctk.CTkLabel(self, text="MIDI再生 録音同期ツール", font=("bold", 16)).pack(pady=20)
        
        self.lbl_file = ctk.CTkLabel(self, text="MIDIファイル: 未選択", text_color="gray")
        self.lbl_file.pack(pady=10)
        
        ctk.CTkButton(self, text="MIDIファイル読み込み", command=self.load_midi).pack(pady=5)
        
        self.btn_start = ctk.CTkButton(self, text="▶ 再生と録音を開始", fg_color="green", command=self.start_process)
        self.btn_start.pack(pady=20)
        
        self.progress_label = ctk.CTkLabel(self, text="待機中...")
        self.progress_label.pack()

        ctk.CTkButton(self, text="保存フォルダを開く", fg_color="#7f8c8d", command=self.open_folder).pack(side="bottom", pady=20)

    def load_midi(self):
        self.midi_path = filedialog.askopenfilename(filetypes=[("MIDI files", "*.mid")])
        if self.midi_path:
            self.lbl_file.configure(text=f"選択済: {os.path.basename(self.midi_path)}", text_color="white")

    def open_folder(self):
        os.startfile(self.rec_dir)

    def start_process(self):
        if not self.midi_path or not self.parent.outport:
            messagebox.showerror("Error", "MIDIファイルまたは出力ポートが未設定です")
            return
        
        self.btn_start.configure(state="disabled")
        threading.Thread(target=self.recording_thread, daemon=True).start()

    def recording_thread(self):
        try:
            mid = MidiFile(self.midi_path)
            
            # 保存用ファイル名の生成
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"{timestamp}_{os.path.basename(self.midi_path).replace('.mid', '.wav')}"
            save_path = os.path.join(self.rec_dir, file_name)

            # オーディオ設定
            p = pyaudio.PyAudio()
            stream = p.open(format=pyaudio.paInt16, channels=2, rate=44100,
                            input=True, input_device_index=self.parent.audio_input_index,
                            frames_per_buffer=1024)
            
            self.parent.log(f"Recording started: {file_name}")
            self.progress_label.configure(text="再生中・録音中...")
            
            frames = []
            stop_event = threading.Event()

            # 録音サブスレッド
            def record_loop():
                while not stop_event.is_set():
                    data = stream.read(1024, exception_on_overflow=False)
                    frames.append(data)

            rec_subthread = threading.Thread(target=record_loop)
            rec_subthread.start()

            # MIDI再生 (Note On/Off, CC, PC すべて送信)
            for msg in mid.play():
                if not self.is_processing and stop_event.is_set(): break
                self.parent.outport.send(msg)

            # 終了処理
            stop_event.set()
            rec_subthread.join()
            
            stream.stop_stream()
            stream.close()
            p.terminate()

            # WAV保存
            with wave.open(save_path, 'wb') as wf:
                wf.setnchannels(2)
                wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
                wf.setframerate(44100)
                wf.writeframes(b''.join(frames))

            self.parent.log(f"Recording finished: {save_path}")
            messagebox.showinfo("Success", "録音が完了しました。")
            
        except Exception as e:
            self.parent.log(f"Recording Error: {e}")
        finally:
            self.progress_label.configure(text="待機中")
            self.btn_start.configure(state="normal")