import os
import threading
import numpy as np
import pygame
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE
from mutagen.mp4 import MP4

try:
    import soundfile as sf
except ImportError:
    sf = None

SAMPLE_RATE = 44100
CHANNELS = 2
CHUNK = 4096
MAX_PCM_SEC = 30 * 60


class AudioEngine:
    def __init__(self):
        pygame.mixer.pre_init(SAMPLE_RATE, -16, CHANNELS, 1024)
        pygame.mixer.init()
        pygame.mixer.music.set_volume(0.7)
        self._volume = 0.7
        self._playing = False
        self._paused = False
        self._current_file = None
        self._duration = 0
        self._pause_time = 0
        self._fft_data = np.zeros(64)
        self._monitor_thread = None
        self._monitoring = False
        self._pcm = None
        self._pcm_len = 0
        self._seek_offset = 0
        self._pending_seek = 0.0
        self._decode_gen = 0
        self._prev_low = None
        self._flux_peak = 1e-6
        self._bass_flux = 0.0
        self._sf = None
        self._band_idx = None
        self._sf_lock = threading.Lock()

    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, val):
        self._volume = max(0.0, min(1.0, val))
        pygame.mixer.music.set_volume(self._volume)

    @property
    def is_playing(self):
        return self._playing and not self._paused

    @property
    def is_paused(self):
        return self._paused

    @property
    def is_loaded(self):
        return self._current_file is not None

    @property
    def duration(self):
        return self._duration

    def get_position(self):
        if not self._playing:
            return max(0.0, self._pending_seek)
        if self._paused:
            return self._pause_time
        elapsed = pygame.mixer.music.get_pos() / 1000.0
        pos = self._seek_offset + elapsed
        if self._duration > 0:
            pos = min(pos, self._duration)
        return max(0, pos)

    def get_fft_data(self):
        return self._fft_data.copy()

    def get_percussion(self):
        return self._bass_flux

    @staticmethod
    def _open_tags(filepath, ext):
        if ext == ".mp3":
            return MP3(filepath)
        if ext == ".flac":
            return FLAC(filepath)
        if ext == ".ogg":
            return OggVorbis(filepath)
        if ext == ".wav":
            return WAVE(filepath)
        if ext in (".m4a", ".mp4", ".aac"):
            return MP4(filepath)
        return None

    def load(self, filepath):
        self.stop()
        ext = os.path.splitext(filepath)[1].lower()
        self._duration = 0
        try:
            audio = self._open_tags(filepath, ext)
            if audio is not None:
                self._duration = audio.info.length
        except Exception:
            self._duration = 0

        pygame.mixer.music.load(filepath)
        self._current_file = filepath
        self._open_stream(filepath)

    def _open_stream(self, filepath):
        with self._sf_lock:
            self._sf = None
            self._band_idx = None
            if sf is None:
                return
            try:
                handle = sf.SoundFile(filepath)
                freqs = np.fft.rfftfreq(CHUNK, 1.0 / handle.samplerate)
                edges = np.geomspace(30.0, 16000.0, 65)
                self._band_idx = np.clip(
                    np.searchsorted(edges, freqs, side="right") - 1, 0, 63,
                )
                self._sf = handle
            except Exception:
                self._sf = None

    def _close_stream(self):
        with self._sf_lock:
            if self._sf is not None:
                try:
                    self._sf.close()
                except Exception:
                    pass
                self._sf = None
                self._band_idx = None

    def _read_block(self, pos_sec):
        with self._sf_lock:
            handle = self._sf
            if handle is None:
                return None
            try:
                start = int(pos_sec * handle.samplerate)
                if start < 0 or start >= len(handle):
                    return None
                handle.seek(start)
                data = handle.read(CHUNK, dtype="float32", always_2d=True)
            except Exception:
                return None
        if len(data) == 0:
            return None
        return data.mean(axis=1)

    def _decode_to_pcm(self, filepath, gen):
        try:
            sound = pygame.mixer.Sound(file=filepath)
            raw = sound.get_raw()
            del sound
            if gen != self._decode_gen or self._current_file != filepath:
                return
            samples = np.frombuffer(raw, dtype=np.int16)
            if CHANNELS == 2:
                mono = (samples[0::2].astype(np.int32) + samples[1::2]) // 2
                pcm = mono.astype(np.int16)
            else:
                pcm = samples.copy()
            if gen == self._decode_gen and self._current_file == filepath:
                self._pcm = pcm
                self._pcm_len = len(pcm)
        except Exception as err:
            if gen == self._decode_gen and self._current_file == filepath:
                print(f"[pulse] spectrum decode failed ({err}); visualizer will idle")
                self._pcm = None
                self._pcm_len = 0

    def play(self):
        if self._current_file is None:
            return
        start = self._pending_seek
        self._pending_seek = 0.0
        try:
            if start > 0:
                pygame.mixer.music.play(start=start)
            else:
                pygame.mixer.music.play()
        except Exception:
            pygame.mixer.music.play()
            start = 0.0
        self._seek_offset = start
        self._playing = True
        self._paused = False
        if not self._monitoring:
            self._monitoring = True
            self._monitor_thread = threading.Thread(target=self._monitor, daemon=True)
            self._monitor_thread.start()

    def pause(self):
        if self._playing and not self._paused:
            self._pause_time = self.get_position()
            pygame.mixer.music.pause()
            self._paused = True

    def resume(self):
        if self._paused:
            self._seek_offset = self._pause_time
            pygame.mixer.music.unpause()
            self._paused = False

    def stop(self):
        pygame.mixer.music.stop()
        self._playing = False
        self._paused = False
        self._current_file = None
        self._pcm = None
        self._pcm_len = 0
        self._fft_data = np.zeros(64)
        self._seek_offset = 0
        self._pending_seek = 0.0
        self._decode_gen += 1
        self._prev_low = None
        self._bass_flux = 0.0
        self._close_stream()

    def seek(self, position_sec):
        if self._current_file and self._duration > 0:
            position_sec = max(0.0, min(position_sec, self._duration))
            was_paused = self._paused
            pygame.mixer.music.play(start=position_sec)
            pygame.mixer.music.set_volume(self._volume)
            self._playing = True
            self._seek_offset = position_sec
            if was_paused:
                self._pause_time = position_sec
                pygame.mixer.music.pause()
                self._paused = True
            else:
                self._paused = False

    def _monitor(self):
        tilt = 1.0 + (np.arange(64) / 63.0) * 2.0
        idle_wait = 0
        while self._monitoring:
            block = None
            if self._playing and not self._paused:
                idle_wait = 0
                block = self._read_block(self.get_position())
                if block is None and self._pcm is not None:
                    pos_sec = self.get_position()
                    start_sample = int(pos_sec * SAMPLE_RATE)
                    if start_sample < self._pcm_len:
                        end_sample = min(start_sample + CHUNK, self._pcm_len)
                        block = self._pcm[start_sample:end_sample].astype(np.float32)
                        block /= 32768.0
            else:
                self._fft_data *= 0.92
                idle_wait += 1
                pygame.time.wait(20 if idle_wait < 25 else 200)
                continue

            if block is not None and len(block) > 0:
                try:
                    spec = np.abs(np.fft.rfft(block))
                    low_n = max(4, int(200.0 / (SAMPLE_RATE / CHUNK)))
                    cur_low = spec[:low_n]
                    if self._prev_low is not None and len(cur_low) == len(self._prev_low):
                        d = cur_low - self._prev_low
                        flux = float(np.sum(d[d > 0])) / (low_n * 32768.0)
                    else:
                        flux = 0.0
                    self._prev_low = cur_low.copy()
                    self._flux_peak = max(self._flux_peak * 0.999, flux, 1e-6)
                    target = min(flux / self._flux_peak, 1.0)
                    rate = 0.7 if target > self._bass_flux else 0.22
                    self._bass_flux += (target - self._bass_flux) * rate

                    band_idx = self._band_idx
                    bands = np.zeros(64)
                    if band_idx is not None:
                        np.maximum.at(bands, band_idx[: len(spec)], spec)
                    mx = float(np.max(bands))
                    if mx > 1e-6:
                        bands = bands / mx
                        bands *= tilt
                        mx2 = float(np.max(bands))
                        if mx2 > 1e-6:
                            bands /= mx2
                    self._fft_data = np.power(np.clip(bands, 0, 1), 0.5)
                except Exception:
                    self._fft_data *= 0.9
                pygame.time.wait(20)
            elif self._playing and not self._paused:
                self._fft_data *= 0.98
                pygame.time.wait(20)
        self._fft_data = np.zeros(64)

    def get_metadata(self, filepath):
        info = {"title": "", "artist": "", "duration": ""}
        try:
            ext = os.path.splitext(filepath)[1].lower()
            audio = self._open_tags(filepath, ext)
            if audio is None:
                info["title"] = os.path.splitext(os.path.basename(filepath))[0]
                return info
            title = audio.get("TIT2") or audio.get("\xa9nam")
            artist = audio.get("TPE1") or audio.get("\xa9ART")
            info["title"] = str(title) if title else os.path.splitext(os.path.basename(filepath))[0]
            info["artist"] = str(artist) if artist else ""
            length = audio.info.length
            mins = int(length // 60)
            secs = int(length % 60)
            info["duration"] = f"{mins}:{secs:02d}"
        except Exception:
            info["title"] = os.path.splitext(os.path.basename(filepath))[0]
        return info

    def cleanup(self):
        self._monitoring = False
        self._pcm = None
        self._close_stream()
        pygame.mixer.music.stop()
        pygame.mixer.quit()
