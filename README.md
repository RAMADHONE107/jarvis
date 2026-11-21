# JARVIS untuk Termux

Asisten suara yang berjalan di Termux. Otaknya adalah sesi OpenCode (`opencode/big-pickle`)
lewat API lokal, lengkap dengan tool MCP `termux-*` untuk mengontrol HP.

## Arsitektur

```
Android SpeechRecognizer (id-ID, lewat termux-speech-to-text)
  -> wake "Hey Jarvis" + perintah dalam satu ucapan
  -> OpenCode API (otak + tool MCP)
  -> Android TTS lewat Termux:API
  -> HUD web di http://127.0.0.1:8769
```

Whisper.cpp tetap ada di `models/` sebagai cadangan offline, tapi **tidak dipakai di jalur utama**
karena transkrip 4 detik audio memakan 12-23 detik di HP ini.

## Refleks cepat

Perintah perangkat yang jelas dijawab langsung tanpa memanggil LLM (terukur **0,1-2,0 detik**):

- baterai / daya → `termux-battery-status`
- jam / waktu → waktu lokal
- putar / buka musik → `am start --user 0 -a android.intent.action.MUSIC_PLAYER`
- buka youtube / kamera / browser → `am start --user 0 ... -p <package>`
- kirim notifikasi → `termux-notification`
- status wifi → `termux-wifi-connectioninfo`

Pertanyaan lain tetap lewat agen OpenCode (terukur ~7 detik).

## TTS tanpa reload

`tts.py` memakai **satu** proses `termux-tts-speak` yang membaca FIFO. Engine Android di-init
sekali saat startup lewat baris kosong (warm-up), sehingga mengantrekan kalimat hanya ~0,06 detik.
Ini berdasarkan `TextToSpeechAPI.java` di repo `termux/termux-api` dan issue #87: memanggil
TTS ulang tiap kalimat perlu ~6-8 detik untuk bind engine.

## Mode obrolan

Setelah wake (ucapan **atau** tombol AKTIFKAN), ada jendela **12 detik** untuk mulai bicara.
Setiap perintah yang diproses memperpanjang jendela jadi **45 detik**, jadi bisa ngobrol
tanpa mengulang "Hey Jarvis". Ucapan di luar jendela diabaikan supaya suara latar tidak
jadi perintah.

## Saat telepon / mikrofon sibuk

Android **melarang** aplikasi pihak ketiga mengakses audio panggilan (`VOICE_CALL` butuh izin
sistem `CAPTURE_AUDIO_OUTPUT`), terutama bila Bluetooth headset aktif. Jadi wake word tidak
bisa dipakai saat telepon. JARVIS tetap merespons lewat notifikasi permanen:

- Ketuk notifikasi **JARVIS siap** → tombol **Tanya** → ketik perintah (Android Direct Reply).
- Tombol **HUD** langsung membuka `http://127.0.0.1:8769`.
- Jawaban ditampilkan ulang di notifikasi dan HUD.
- Bila wake hanya terdengar "hey" berulang, JARVIS otomatis menandai status
  "Mikrofon sibuk" dan berhenti membunyikan beep.

## Catatan riset

- `termux/termux-api` → `TextToSpeechAPI.java` + issue #87: FIFO worker untuk TTS.
- `k2-fsa/sherpa-onnx` punya keyword spotting untuk wake word; belum dipakai karena
  SpeechRecognizer + refleks sudah cukup. Perlu benchmark terpisah sebelum dipindah.
- OpenCode punya `GET /api/event` dengan `session.text.delta` (potensi mulai bicara lebih awal),
  tapi autentikasinya tidak menerima password `service.json` lewat header/curl dari bridge ini.

## Pakai

```sh
jarvis                 # jalankan asisten (wake word aktif)
jarvis-status          # cek model, sesi otak, dan HUD
jarvis-ask "..."       # tanya langsung tanpa mikrofon
jarvis-say "..."       # suruh JARVIS bicara (dipakai otak)
```

Buka HUD di browser: `http://127.0.0.1:8769`. Tombol **AKTIFKAN** menyalakan mode dengar,
kolom teks bisa dipakai kalau mikrofon belum siap.

## Prasyarat manual (sekali)

1. Pasang **Termux:API**: APK ada di `/sdcard/Download/termux-api.apk`
   (versi F-Droid, ditandatangani kunci yang sama dengan Termux terpasang, jadi tampil sebagai update).
   Izinkan "Install unknown apps" saat diminta.
2. Beri izin **Microphone** ke aplikasi Termux dan Termux:API
   (Settings -> Apps -> Termux / Termux API -> Permissions).
3. Matikan battery optimization untuk Termux supaya wake word tetap hidup.
4. Jalankan `pactl load-module module-sles-source` sekali (atau biarkan `jarvis` yang mencoba).
5. Model whisper.cpp **tidak disertakan** di repo GitHub karena ukurannya (>100 MB per file).
   Untuk cadangan offline, unduh `ggml-tiny.bin` / `ggml-base.bin` ke folder `models/` dan
   siapkan whisper.cpp sendiri. Jalur utama (Android SpeechRecognizer) tidak memerlukannya.

## Struktur

- `brain.py` — jembatan ke agen OpenCode
- `mic.py` — stream mikrofon 16 kHz
- `stt.py` — whisper.cpp + model GGUF
- `tts.py` — Android TTS
- `hud.py` / `hud.html` — HUD web SSE
- `jarvis.py` — orchestrator wake -> STT -> otak -> TTS
- `bin/` — script CLI
- `models/` — ggml-tiny.bin (wake) dan ggml-base.bin (STT)
