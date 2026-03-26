import cv2
import json
import math
import os
import random
from typing import List, Optional, Tuple

import numpy as np


try:
	from src.encrypt import A51
except ImportError:
	from encrypt import A51


MAGIC = b"STEG"


def bytes_to_bits(data: bytes) -> List[int]:
	bits: List[int] = []
	for byte in data:
		for i in range(8):
			bits.append((byte >> (7 - i)) & 1)
	return bits


def calculate_capacity(frames) -> int:
	if not frames:
		raise ValueError("Video tidak memiliki frame untuk dihitung kapasitasnya")
	h, w, _ = frames[0].shape
	return len(frames) * h * w * 3


def build_payload(
	secret_path: str,
	payload_type: str,
	encrypt_payload: bool,
	a51_key: Optional[str],
	mode: str,
) -> bytes:
	with open(secret_path, "rb") as f:
		payload_bytes = f.read()

	norm_type = "file" if payload_type == "file" else "text"
	file_name = os.path.basename(secret_path) if norm_type == "file" else ""

	if encrypt_payload:
		payload_bytes = A51(a51_key).encrypt(payload_bytes)

	metadata = {
		"type": norm_type,
		"filename": file_name,
		"size": len(payload_bytes),
		"encrypted": bool(encrypt_payload),
		"mode": "random" if mode == "random" else "sequential",
	}
	meta_bytes = json.dumps(metadata).encode("utf-8")

	header = bytearray()
	header += MAGIC
	header += len(meta_bytes).to_bytes(4, "big")
	header += meta_bytes

	return bytes(header) + payload_bytes


def read_video_frames(video_path: str):
	cap = cv2.VideoCapture(video_path)
	if not cap.isOpened():
		raise IOError(f"Tidak bisa membuka video: {video_path}")

	fps = cap.get(cv2.CAP_PROP_FPS)
	width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
	height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

	frames = []
	while cap.isOpened():
		ret, frame = cap.read()
		if not ret:
			break
		frames.append(frame)

	cap.release()
	return frames, fps, width, height


def embed_payload_bits(
	frames,
	payload_bits: List[int],
	mode: str,
	stego_key: Optional[str],
):
	frame_capacity = calculate_capacity(frames) // len(frames)
	total_capacity = frame_capacity * len(frames)

	if len(payload_bits) > total_capacity:
		raise ValueError(
			f"Payload terlalu besar untuk video cover! Kapasitas: {total_capacity} bit, payload: {len(payload_bits)} bit"
		)

	if mode == "random" and not stego_key:
		raise ValueError("Stego-key wajib diisi untuk mode random")

	if mode == "sequential":
		for bit_index, bit in enumerate(payload_bits):
			frame_idx = bit_index // frame_capacity
			pixel_idx = bit_index % frame_capacity
			flat = frames[frame_idx].reshape(-1)
			flat[pixel_idx] = (int(flat[pixel_idx]) & ~1) | bit
		return

	bit_index = 0
	for frame_idx, frame in enumerate(frames):
		if bit_index >= len(payload_bits):
			break

		positions = list(range(frame_capacity))
		rng = random.Random(f"{stego_key}:{frame_idx}")
		rng.shuffle(positions)

		flat = frame.reshape(-1)
		bits_this_frame = min(frame_capacity, len(payload_bits) - bit_index)
		for local_idx in range(bits_this_frame):
			pixel_idx = positions[local_idx]
			bit = payload_bits[bit_index + local_idx]
			flat[pixel_idx] = (int(flat[pixel_idx]) & ~1) | bit

		bit_index += bits_this_frame


def compute_mse_psnr(original_frames, stego_frames) -> Tuple[float, float]:
	if len(original_frames) != len(stego_frames):
		raise ValueError("Jumlah frame original dan stego tidak sama")

	total_pixels = 0
	sum_square_error = 0.0

	for orig, stego in zip(original_frames, stego_frames):
		if orig.shape != stego.shape:
			raise ValueError("Dimensi frame original dan stego tidak cocok")
		diff = orig.astype(np.float32) - stego.astype(np.float32)
		sum_square_error += float(np.sum(np.square(diff)))
		total_pixels += orig.size

	if total_pixels == 0:
		raise ValueError("Video kosong sehingga tidak bisa menghitung MSE/PSNR")

	mse = sum_square_error / total_pixels
	psnr = float("inf") if mse == 0 else 10.0 * math.log10((255.0 ** 2) / mse)
	return mse, psnr


def compute_rgb_hist(frames) -> dict:
	if not frames:
		raise ValueError("Video kosong sehingga histogram tidak bisa dihitung")

	hist = {"b": np.zeros(256, dtype=np.int64), "g": np.zeros(256, dtype=np.int64), "r": np.zeros(256, dtype=np.int64)}
	for frame in frames:
		for idx, key in enumerate(("b", "g", "r")):
			channel_hist = cv2.calcHist([frame], [idx], None, [256], [0, 256]).flatten().astype(np.int64)
			hist[key] += channel_hist

	return {k: v.tolist() for k, v in hist.items()}


def write_video_frames(
	output_path: str,
	fps: float,
	width: int,
	height: int,
	frames,
	preferred_codec: Optional[str] = None,
):
	if not output_path:
		raise ValueError("Output path video stego kosong")
	parent = os.path.dirname(output_path)
	if parent:
		os.makedirs(parent, exist_ok=True)
	codec_candidates = ["FFV1", "HFYU"]
	if preferred_codec:
		# Try the preferred codec first while still falling back to defaults.
		codec_candidates = [preferred_codec] + [c for c in codec_candidates if c != preferred_codec]
	out = None
	selected_codec = None

	for codec in codec_candidates:
		fourcc = cv2.VideoWriter_fourcc(*codec)
		writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
		if writer.isOpened():
			out = writer
			selected_codec = codec
			break

	if out is None:
		raise RuntimeError(
			"Tidak bisa membuka VideoWriter lossless (FFV1/HFYU). "
			"LSB steganografi butuh codec lossless agar data tidak rusak."
		)

	for frame in frames:
		out.write(frame)
	out.release()
	print(f"Codec stego yang dipakai: {selected_codec}")


def validate_video(output_path: str):
	cap = cv2.VideoCapture(output_path)
	if not cap.isOpened():
		raise IOError(f"Stego-video tidak bisa dibuka: {output_path}")
	ret, _ = cap.read()
	cap.release()
	if not ret:
		raise IOError(f"Stego-video korup atau kosong: {output_path}")

def insert_message_to_video(
	video_path: str,
	secret_path: str,
	output_path: str,
	payload_type: str = "file",
	encrypt_payload: bool = False,
	a51_key: Optional[str] = None,
	mode: str = "sequential",
	stego_key: Optional[str] = None,
	preferred_codec: Optional[str] = None,
):

	payload = build_payload(secret_path, payload_type, encrypt_payload, a51_key, mode)
	payload_bits = bytes_to_bits(payload)
	frames, fps, width, height = read_video_frames(video_path)
	if not frames:
		raise ValueError("Video kosong, tidak ada frame untuk disisipi")

	total_capacity = calculate_capacity(frames)
	if len(payload_bits) > total_capacity:
		raise ValueError(
			f"Payload terlalu besar. Kapasitas: {total_capacity} bit, payload: {len(payload_bits)} bit"
		)

	original_frames = [frame.copy() for frame in frames]
	embed_payload_bits(frames, payload_bits, mode, stego_key)

	mse, psnr = compute_mse_psnr(original_frames, frames)
	hist_original = compute_rgb_hist(original_frames)
	hist_stego = compute_rgb_hist(frames)

	write_video_frames(output_path, fps, width, height, frames, preferred_codec=preferred_codec)
	validate_video(output_path)

	result = {
		"output_path": output_path,
		"payload_bits": len(payload_bits),
		"capacity_bits": total_capacity,
		"mse": mse,
		"psnr": psnr,
		"hist_original": hist_original,
		"hist_stego": hist_stego,
		"frame_count": len(frames),
	}

	print(
		f"Penyisipan selesai. Stego-video: {output_path}\n"
		f"Kapasitas: {total_capacity} bit | Payload: {len(payload_bits)} bit | MSE: {mse:.6f} | PSNR: {psnr:.2f} dB"
	)
	return result
