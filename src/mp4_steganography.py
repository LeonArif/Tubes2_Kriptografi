import os
import shutil
import subprocess
import tempfile
from typing import List, Optional

import cv2

try:
    from src.encrypt import A51
    from src.insertion import (
        MAGIC,
        build_payload,
        bytes_to_bits,
        embed_payload_bits,
        read_video_frames,
    )
    from src.extraction import (
        bits_to_bytes,
        collect_lsb_stream,
        extract_message_from_video,
        parse_header,
        read_bits_by_mode,
    )
except ImportError:
    from encrypt import A51
    from insertion import (
        MAGIC,
        build_payload,
        bytes_to_bits,
        embed_payload_bits,
        read_video_frames,
    )
    from extraction import (
        bits_to_bytes,
        collect_lsb_stream,
        extract_message_from_video,
        parse_header,
        read_bits_by_mode,
    )

def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _write_frames_as_png(frames, frames_dir: str):
    os.makedirs(frames_dir, exist_ok=True)
    for i, frame in enumerate(frames):
        path = os.path.join(frames_dir, f"frame_{i:08d}.png")
        cv2.imwrite(path, frame, [cv2.IMWRITE_PNG_COMPRESSION, 0])


def _write_lossless_mp4_ffmpeg(
    frames_dir: str,
    output_mp4: str,
    fps: float,
    width: int,
    height: int,
) -> bool:
    pattern = os.path.join(frames_dir, "frame_%08d.png")

    attempts = [
        [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", pattern,
            "-c:v", "libx264rgb",
            "-preset", "ultrafast",
            "-qp", "0",
            output_mp4,
        ],
        [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", pattern,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-qp", "0",
            "-pix_fmt", "yuv444p",
            output_mp4,
        ],
    ]

    for cmd in attempts:
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=600,
            )
            if result.returncode == 0:
                print(f"[MP4] ffmpeg sukses dengan codec: {cmd[cmd.index('-c:v') + 1]}")
                return True
        except Exception:
            continue

    return False


def _write_stego_avi(output_path: str, fps: float, width: int, height: int, frames):
    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    for codec in ["FFV1", "HFYU"]:
        fourcc = cv2.VideoWriter_fourcc(*codec)
        writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        if writer.isOpened():
            for frame in frames:
                writer.write(frame)
            writer.release()
            print(f"[MP4 fallback] Disimpan sebagai AVI dengan codec: {codec}")
            return
    raise RuntimeError(
        "Tidak bisa membuat VideoWriter lossless (FFV1/HFYU). "
        "Install OpenCV dengan dukungan FFV1."
    )


def insert_message_to_mp4(
    video_path: str,
    secret_path: str,
    output_path: str,
    payload_type: str = "file",
    encrypt_payload: bool = False,
    a51_key: Optional[str] = None,
    mode: str = "sequential",
    stego_key: Optional[str] = None,
) -> dict:
    frames, fps, width, height = read_video_frames(video_path)
    payload      = build_payload(secret_path, payload_type, encrypt_payload, a51_key, mode)
    payload_bits = bytes_to_bits(payload)
    frame_capacity = frames[0].shape[0] * frames[0].shape[1] * 3
    total_capacity = len(frames) * frame_capacity
    if len(payload_bits) > total_capacity:
        raise ValueError(
            f"Payload terlalu besar! "
            f"Kapasitas: {total_capacity // 8} bytes, "
            f"Dibutuhkan: {len(payload_bits) // 8} bytes."
        )
    embed_payload_bits(frames, payload_bits, mode, stego_key)

    base_no_ext = os.path.splitext(output_path)[0]
    if base_no_ext.endswith("_stego_mp4"):
        avi_base = base_no_ext[: -len("_stego_mp4")] + "_stego_mp4"
    else:
        avi_base = base_no_ext
    avi_output = avi_base + ".avi"
    actual_output = output_path
    codec_used    = "avi_fallback"

    if _ffmpeg_available():
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_frames_as_png(frames, tmpdir)
            ok = _write_lossless_mp4_ffmpeg(tmpdir, output_path, fps, width, height)

        if ok:
            codec_used    = "mp4_lossless"
            actual_output = output_path
        else:
            _write_stego_avi(avi_output, fps, width, height, frames)
            codec_used    = "avi_fallback"
            actual_output = avi_output
    else:
        _write_stego_avi(avi_output, fps, width, height, frames)
        codec_used    = "avi_fallback"
        actual_output = avi_output

    print(f"[MP4 Bonus] Stego video: {actual_output} | codec: {codec_used}")
    return {
        "output_path":   output_path,
        "actual_output": actual_output,
        "codec_used":    codec_used,
    }

def extract_message_from_mp4(
    stego_video_path: str,
    a51_key: Optional[str] = None,
    stego_key: Optional[str] = None,
    save_as_path: Optional[str] = None,
    output_dir: str = "output",
) -> dict:
    return extract_message_from_video(
        stego_video_path=stego_video_path,
        a51_key=a51_key,
        stego_key=stego_key,
        save_as_path=save_as_path,
        output_dir=output_dir,
        prompt_save_as=False,
    )


def get_mp4_capacity(video_path: str) -> int:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise IOError(f"Tidak bisa membuka video: {video_path}")
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width       = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height      = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return (frame_count * height * width * 3) // 8