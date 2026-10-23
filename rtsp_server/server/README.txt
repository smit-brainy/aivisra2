AIVISRA VIRTUAL CCTV & ENTERPRISE NVR RTSP GENERATOR
=====================================================

WHAT IT DOES
Simulates real enterprise CCTV cameras & NVR systems (Hikvision, Dahua, Axis)
on either Windows or Linux for realistic, zero-lag testing of AIVISRA StreamCore.

FEATURES
1. Enterprise NVR Proxy Mode (Recommended - Zero Lag):
   - MediaMTX acts as an in-memory NVR proxy.
   - Master video is published ONCE to MediaMTX.
   - MediaMTX clones packets in memory to cam001, cam002, ..., cam050 with ~0% CPU.
   - Delivers steady, jitter-free 25 FPS RTSP streams identical to commercial NVRs.

2. Multi-Video Customization:
   - Assign DIFFERENT video files to different cameras (e.g. cam001=entrance.mp4, cam002=parking.mp4).
   - Or select a Video Folder: automatically cycles and distributes videos across all cameras!
   - Full camera-to-video mapping table in the UI.

3. CCTV Standard Zero-Latency Transcoding:
   - Encodes with: -preset ultrafast -tune zerolatency -bf 0 -g 25
   - Zero B-frames and fixed 1-second keyframe interval eliminate decoder buffering.

4. Cross-Platform:
   - Windows: Self-contained AIVISRA_Virtual_CCTV.exe (no Python or installation needed).
   - Linux: Native GUI or headless CLI mode (START_APP.sh).

-----------------------------------------------------
RUNNING ON WINDOWS (ALL-IN-ONE EXE)
-----------------------------------------------------
1. Double-click AIVISRA_Virtual_CCTV.exe.
2. Select your video or folder, choose camera count, and click "Start RTSP Cameras".
3. Copy URLs or click "Export StreamCore app.yaml" to generate camera configurations.

-----------------------------------------------------
RUNNING ON LINUX
-----------------------------------------------------
Desktop GUI:
  ./START_APP.sh
  or: python3 app.py

Headless CLI (e.g. SSH / Server):
  # Single video with NVR proxy (10 cameras):
  python3 app.py --cli --video /path/to/video.mp4 --count 10

  # Multi-video folder (auto-distributes videos to cameras):
  python3 app.py --cli --folder /path/to/videos_folder --count 10

  # Custom options:
  python3 app.py --cli --video cafe.mp4 --count 20 --port 8554 --mode transcode --fps 25

-----------------------------------------------------
TESTING THE STREAMS
-----------------------------------------------------
From another PC or same machine:
  ffplay -rtsp_transport tcp rtsp://<LAN-IP>:8554/cam001
WebRTC low-latency browser view:
  http://<LAN-IP>:8889/cam001/

-----------------------------------------------------
FILES
-----------------------------------------------------
AIVISRA_Virtual_CCTV.exe  Windows standalone GUI (FFmpeg & MediaMTX embedded)
app.py                    Main Python application (GUI & CLI)
START_APP.sh              Linux launch script
START_APP.bat             Windows Python launch script
SETUP_WINDOWS.ps1         Windows tool downloader & firewall setup
mediamtx.yml              Active MediaMTX configuration
tools/                    Embedded binaries (ffmpeg, mediamtx)
logs/                     MediaMTX and per-stream logs
