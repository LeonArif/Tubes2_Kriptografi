import cv2
import os
import random
from typing import List, Optional


try:
	from src.encrypt import A51
except ImportError:
	from encrypt import A51


def bytes_to_bits(data: bytes) -> List[int]:
	bits: List[int] = []
	for byte in data:
		for i in range(8):
			bits.append((byte >> (7 - i)) & 1)
	return bits


def build_payload(
	secret_path: str,
	encrypt_payload: bool,
	a51_key: Optional[str],
	mode: str,
) -> bytes:
	with open(secret_path, "rb") as f:
		secret_data = f.read()

	secret_size = len(secret_data)
	secret_ext = os.path.splitext(secret_path)[1][1:]
	secret_name = os.path.basename(secret_path)
	is_file = True

	if encrypt_payload:
		secret_data = A51(a51_key).encrypt(secret_data)

	header = bytearray()
	header += b"STEG"
	header += (b"1" if is_file else b"0")
	header += bytes([len(secret_ext)])
	header += secret_ext.encode()
	header += bytes([len(secret_name)])
	header += secret_name.encode()
	header += secret_size.to_bytes(4, "big")
	header += (b"1" if encrypt_payload else b"0")
	header += (b"1" if mode == "random" else b"0")

	return bytes(header) + secret_data


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
	h, w, _ = frames[0].shape
	frame_capacity = h * w * 3
	total_capacity = len(frames) * frame_capacity

	if len(payload_bits) > total_capacity:
		raise ValueError("Payload terlalu besar untuk video cover!")

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


def write_video_frames(output_path: str, fps: float, width: int, height: int, frames):
	codec_candidates = ["FFV1", "HFYU"]
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

def insert_message_to_video(
	video_path: str,
	secret_path: str,
	output_path: str,
	encrypt_payload: bool = False,
	a51_key: Optional[str] = None,
	mode: str = "sequential",
	stego_key: Optional[str] = None
):

	payload = build_payload(secret_path, encrypt_payload, a51_key, mode)
	payload_bits = bytes_to_bits(payload)
	frames, fps, width, height = read_video_frames(video_path)
	embed_payload_bits(frames, payload_bits, mode, stego_key)
	write_video_frames(output_path, fps, width, height, frames)

	print(f"Penyisipan selesai. Stego-video: {output_path}")
