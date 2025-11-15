# import sounddevice as sd
# import webrtcvad
# import numpy as np
# import io
# import wavio
# import threading
# import queue
# import time
# from typing import Optional


# class ContinuousAudioRecorder:
#     """
#     Continuous audio recorder with duplicate prevention
#     FIXED: Prevents sending duplicate chunks that cause processing loops
#     """

#     def __init__(self, silence_threshold: float = 0.3, fs: int = 16000):
#         self.fs = fs
#         self.silence_threshold = silence_threshold
#         self.frame_duration = 20  # 20ms frames
#         self.frame_samples = int(fs * self.frame_duration / 1000)

#         self.vad = webrtcvad.Vad(3)
#         self.audio_queue = queue.Queue(maxsize=5)  # Limit queue size to prevent overflow
#         self.is_running = False
#         self.thread = None

#         # Find Stereo Mix device
#         self.device_index = self._find_stereo_mix()

#     def _find_stereo_mix(self) -> Optional[int]:
#         """Find Stereo Mix or loopback device"""
#         try:
#             devices = sd.query_devices()
#             for i, dev in enumerate(devices):
#                 if "stereo mix" in dev["name"].lower() and dev["max_input_channels"] > 0:
#                     print(f"✓ Found audio device: {dev['name']}")
#                     return i
#             raise RuntimeError("Stereo Mix not found! Enable it in Windows Sound Settings.")
#         except Exception as e:
#             print(f"Device detection error: {e}")
#             return None

#     def _recording_worker(self):
#         """
#         Background thread that continuously records audio
#         FIXED: Prevents duplicate chunk generation with hash-based deduplication
#         """
#         buffer = []
#         silence_duration = 0
#         speech_detected = False
#         min_speech_duration = 0.4
        
#         # Continuous recording buffer
#         continuous_buffer = []
#         last_chunk_time = time.time()
#         chunk_interval = 3.0  # Increased to 3s to reduce unnecessary chunks
        
#         # Track last sent chunk to prevent duplicates
#         last_sent_hash = None
#         speech_hash_history = []  # Track recent speech hashes

#         try:
#             with sd.InputStream(
#                 samplerate=self.fs,
#                 channels=1,
#                 dtype="int16",
#                 device=self.device_index,
#                 blocksize=self.frame_samples,
#                 latency='low'
#             ) as stream:

#                 while self.is_running:
#                     try:
#                         frame, overflowed = stream.read(self.frame_samples)

#                         if overflowed:
#                             print("⚠️  Audio buffer overflow")

#                         # ALWAYS append to continuous buffer
#                         continuous_buffer.append(frame.copy())
                        
#                         frame_bytes = frame.tobytes()
#                         is_speech = self.vad.is_speech(frame_bytes, self.fs)

#                         # Mode 1: VAD-based speech detection
#                         if is_speech:
#                             buffer.append(frame.copy())
#                             silence_duration = 0
#                             speech_detected = True
#                         else:
#                             if speech_detected:
#                                 if silence_duration < 0.15:
#                                     buffer.append(frame.copy())

#                                 silence_duration += self.frame_duration / 1000

#                                 speech_duration = len(buffer) * self.frame_duration / 1000
                                
#                                 if (silence_duration > self.silence_threshold and 
#                                     speech_duration >= min_speech_duration and 
#                                     buffer):
                                    
#                                     audio_data = np.concatenate(buffer, axis=0)
                                    
#                                     # Generate hash to prevent duplicates (use more data for better uniqueness)
#                                     chunk_hash = hash(audio_data.tobytes()[:2000])  # Hash first 2000 bytes
                                    
#                                     # Check against recent history (not just last one)
#                                     if chunk_hash not in speech_hash_history:
#                                         wav_buffer = io.BytesIO()
#                                         wavio.write(wav_buffer, audio_data, self.fs, sampwidth=2)
#                                         wav_buffer.seek(0)
#                                         wav_buffer.name = "speech_segment.wav"

#                                         try:
#                                             # Use put with timeout instead of put_nowait
#                                             self.audio_queue.put(wav_buffer, timeout=0.1)
                                            
#                                             # Update hash history
#                                             speech_hash_history.append(chunk_hash)
#                                             if len(speech_hash_history) > 10:
#                                                 speech_hash_history.pop(0)
                                            
#                                             last_sent_hash = chunk_hash
#                                             print(f"✓ Speech segment queued: {speech_duration:.1f}s")
#                                         except queue.Full:
#                                             print("⚠️  Audio queue full, dropping speech segment")
#                                     else:
#                                         print("⏭️  Duplicate speech segment prevented")

#                                     buffer = []
#                                     silence_duration = 0
#                                     speech_detected = False
                        
#                         # Mode 2: Time-based chunks (REDUCED frequency to minimize load)
#                         # Only send if queue is empty and enough time has passed
#                         current_time = time.time()
#                         if ((current_time - last_chunk_time) >= chunk_interval and 
#                             continuous_buffer and 
#                             self.audio_queue.qsize() == 0):  # Only if queue is completely empty
                            
#                             audio_data = np.concatenate(continuous_buffer, axis=0)
                            
#                             # Skip if too similar to recent speech segments
#                             chunk_hash = hash(audio_data.tobytes()[:2000])
                            
#                             if chunk_hash not in speech_hash_history:
#                                 wav_buffer = io.BytesIO()
#                                 wavio.write(wav_buffer, audio_data, self.fs, sampwidth=2)
#                                 wav_buffer.seek(0)
#                                 wav_buffer.name = "continuous_chunk.wav"
                                
#                                 try:
#                                     self.audio_queue.put(wav_buffer, timeout=0.1)
#                                     duration = len(continuous_buffer) * self.frame_duration / 1000
#                                     print(f"✓ Continuous chunk queued: {duration:.1f}s")
#                                 except queue.Full:
#                                     print("⚠️  Audio queue full, dropping continuous chunk")
#                             else:
#                                 print("⏭️  Duplicate continuous chunk prevented")
                            
#                             continuous_buffer = []
#                             last_chunk_time = current_time

#                     except Exception as e:
#                         print(f"❌ Recording frame error: {e}")
#                         continue

#         except Exception as e:
#             print(f"❌ Recording worker error: {e}")
#         finally:
#             print("🔴 Recording worker stopped")

#     def start(self):
#         """Start background recording"""
#         if self.is_running:
#             print("⚠️  Recorder already running")
#             return

#         print("🎙️  Starting audio recorder thread...")
#         self.is_running = True
#         self.thread = threading.Thread(target=self._recording_worker, daemon=True, name="AudioRecorder")
#         self.thread.start()
#         print("✅ Audio recorder started (continuous mode with deduplication)")
        
#         # Give it a moment to initialize
#         time.sleep(0.2)
        
#         if not self.thread.is_alive():
#             print("❌ WARNING: Audio recorder thread died immediately!")
#             raise RuntimeError("Audio recorder thread failed to start")
#         else:
#             print("✅ Audio recorder thread is alive and running")

#     def stop(self):
#         """Stop background recording"""
#         if not self.is_running:
#             return
            
#         self.is_running = False
#         if self.thread and self.thread.is_alive():
#             self.thread.join(timeout=2)
        
#         # Clear any remaining items in queue
#         while not self.audio_queue.empty():
#             try:
#                 item = self.audio_queue.get_nowait()
#                 if hasattr(item, 'close'):
#                     item.close()
#             except queue.Empty:
#                 break
        
#         print("🔴 Audio recorder stopped")

#     def get_audio_chunk(self) -> Optional[io.BytesIO]:
#         """
#         Get next available audio chunk
#         Returns None if no chunk available
#         """
#         try:
#             return self.audio_queue.get(timeout=0.1)
#         except queue.Empty:
#             return None


# # Legacy function for backward compatibility
# def record_until_pause(silence_threshold: float = 0.5, fs: int = 16000) -> Optional[io.BytesIO]:
#     """
#     Legacy function - records until pause detected.
#     For better performance, use ContinuousAudioRecorder instead.
#     """
#     vad = webrtcvad.Vad(3)

#     try:
#         devices = sd.query_devices()
#         stereo_mix_index = next(
#             (i for i, dev in enumerate(devices)
#              if "stereo mix" in dev["name"].lower() and dev["max_input_channels"] > 0),
#             None
#         )

#         if stereo_mix_index is None:
#             raise RuntimeError("Stereo Mix device not found!")

#         frame_duration = 20
#         frame_samples = int(fs * frame_duration / 1000)
#         buffer = []
#         silence_duration = 0

#         with sd.InputStream(samplerate=fs, channels=1, dtype="int16", 
#                           device=stereo_mix_index, latency='low') as stream:
#             while True:
#                 frame, _ = stream.read(frame_samples)
#                 frame_bytes = frame.tobytes()
#                 is_speech = vad.is_speech(frame_bytes, fs)

#                 if is_speech:
#                     buffer.append(frame.copy())
#                     silence_duration = 0
#                 else:
#                     silence_duration += frame_duration / 1000
#                     if silence_duration > silence_threshold and buffer:
#                         break

#         if not buffer:
#             return None

#         audio_data = np.concatenate(buffer, axis=0)
#         wav_buffer = io.BytesIO()
#         wavio.write(wav_buffer, audio_data, fs, sampwidth=2)
#         wav_buffer.seek(0)
#         wav_buffer.name = "question.wav"
#         return wav_buffer

#     except Exception as e:
#         print(f"Audio recording error: {e}")
#         return None