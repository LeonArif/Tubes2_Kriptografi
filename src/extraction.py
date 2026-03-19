import os
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import cv2

try:
	from src.encrypt import A51
except ImportError:
	from encrypt import A51


MAGIC = b"STEG"


@dataclass
class PayloadHeader:
	is_file: bool
	file_ext: str
	file_name: str
	payload_size: int
	is_encrypted: bool
	is_random_mode: bool


def bits_to_bytes(bits: List[int]) -> bytes:
	out = bytearray()
	for i in range(0, len(bits), 8):
		byte = 0
		for j in range(8):
			byte <<= 1
			if i + j < len(bits):
				byte |= bits[i + j] & 1
		out.append(byte)
	return bytes(out)


def collect_lsb_stream(stego_video_path: str) -> Tuple[List[int], int]:
	cap = cv2.VideoCapture(stego_video_path)
	if not cap.isOpened():
		raise IOError(f"Tidak bisa membuka video: {stego_video_path}")

	lsb_stream: List[int] = []
	frame_capacity = 0
	while cap.isOpened():
		ret, frame = cap.read()
		if not ret:
			break
		if frame_capacity == 0:
			h, w, _ = frame.shape
			frame_capacity = h * w * 3
		flat = frame.reshape(-1)
		lsb_stream.extend([int(v) & 1 for v in flat])

	cap.release()
	if frame_capacity == 0:
		raise ValueError("Video kosong, tidak ada frame untuk diekstrak")
	return lsb_stream, frame_capacity


def frame_random_positions(frame_capacity: int, stego_key: str, frame_idx: int) -> List[int]:
	positions = list(range(frame_capacity))
	rng = random.Random(f"{stego_key}:{frame_idx}")
	rng.shuffle(positions)
	return positions


def normalize_save_path(typed_path: str, output_dir: str, default_path: str) -> str:
	if not typed_path:
		return default_path
	if os.path.isabs(typed_path):
		return typed_path
	# Relative path from prompt is stored inside output_dir, not current working directory.
	return os.path.join(output_dir, typed_path)


def build_unique_text_path(output_dir: str, stego_video_path: str) -> str:
	os.makedirs(output_dir, exist_ok=True)
	base_name = os.path.splitext(os.path.basename(stego_video_path))[0] or "extracted"
	candidate = os.path.join(output_dir, f"{base_name}_pesan.txt")
	if not os.path.exists(candidate):
		return candidate

	idx = 1
	while True:
		candidate = os.path.join(output_dir, f"{base_name}_pesan_{idx}.txt")
		if not os.path.exists(candidate):
			return candidate
		idx += 1


def read_bits_by_mode(
	lsb_stream: List[int],
	mode: str,
	start_payload_idx: int,
	bit_count: int,
	frame_capacity: int,
	stego_key: Optional[str],
	random_map_cache: Optional[Dict[int, List[int]]] = None,
) -> List[int]:
	end_payload_idx = start_payload_idx + bit_count
	if end_payload_idx > len(lsb_stream):
		raise ValueError("Data payload melebihi kapasitas bit video")

	if mode == "sequential":
		return lsb_stream[start_payload_idx:end_payload_idx]

	if stego_key is None:
		raise ValueError("Stego-key wajib untuk membaca mode random")

	if random_map_cache is None:
		random_map_cache = {}

	bits: List[int] = []
	for payload_idx in range(start_payload_idx, end_payload_idx):
		frame_idx = payload_idx // frame_capacity
		local_payload_idx = payload_idx % frame_capacity

		if frame_idx not in random_map_cache:
			random_map_cache[frame_idx] = frame_random_positions(frame_capacity, stego_key, frame_idx)

		stream_idx = frame_idx * frame_capacity + random_map_cache[frame_idx][local_payload_idx]
		bits.append(lsb_stream[stream_idx])

	return bits


def parse_header(
	lsb_stream: List[int],
	mode: str,
	frame_capacity: int,
	stego_key: Optional[str] = None,
) -> Tuple[PayloadHeader, int]:
	idx = 0
	random_map_cache: Dict[int, List[int]] = {}

	def read_bytes(n_bytes: int) -> bytes:
		nonlocal idx
		bits = read_bits_by_mode(
			lsb_stream=lsb_stream,
			mode=mode,
			start_payload_idx=idx,
			bit_count=n_bytes * 8,
			frame_capacity=frame_capacity,
			stego_key=stego_key,
			random_map_cache=random_map_cache,
		)
		idx += n_bytes * 8
		return bits_to_bytes(bits)

	magic = read_bytes(4)
	if magic != MAGIC:
		raise ValueError("Magic header tidak cocok")

	is_file = read_bytes(1) == b"1"
	ext_len = int.from_bytes(read_bytes(1), "big")
	file_ext = read_bytes(ext_len).decode("utf-8", errors="replace") if ext_len > 0 else ""
	name_len = int.from_bytes(read_bytes(1), "big")
	file_name = read_bytes(name_len).decode("utf-8", errors="replace") if name_len > 0 else ""
	payload_size = int.from_bytes(read_bytes(4), "big")
	is_encrypted = read_bytes(1) == b"1"
	is_random_mode = read_bytes(1) == b"1"

	if payload_size < 0:
		raise ValueError("Ukuran payload tidak valid")

	header = PayloadHeader(
		is_file=is_file,
		file_ext=file_ext,
		file_name=file_name,
		payload_size=payload_size,
		is_encrypted=is_encrypted,
		is_random_mode=is_random_mode,
	)
	return header, idx


def extract_message_from_video(
	stego_video_path: str,
	a51_key: Optional[str] = None,
	stego_key: Optional[str] = None,
	save_as_path: Optional[str] = None,
	output_dir: str = "output",
	prompt_save_as: bool = True,
):
	lsb_stream, frame_capacity = collect_lsb_stream(stego_video_path)
	total_bits = len(lsb_stream)

	seq_result = None
	rand_result = None

	try:
		seq_result = parse_header(
			lsb_stream=lsb_stream,
			mode="sequential",
			frame_capacity=frame_capacity,
		)
	except Exception:
		seq_result = None

	if stego_key is not None:
		try:
			rand_result = parse_header(
				lsb_stream=lsb_stream,
				mode="random",
				frame_capacity=frame_capacity,
				stego_key=stego_key,
			)
		except Exception:
			rand_result = None

	selected_mode = "sequential"
	selected_header = None
	header_bit_len = 0

	if seq_result is not None and not seq_result[0].is_random_mode:
		selected_header, header_bit_len = seq_result
		selected_mode = "sequential"
	elif rand_result is not None and rand_result[0].is_random_mode:
		selected_header, header_bit_len = rand_result
		selected_mode = "random"
	elif seq_result is not None:
		selected_header, header_bit_len = seq_result
		selected_mode = "sequential"
	elif rand_result is not None:
		selected_header, header_bit_len = rand_result
		selected_mode = "random"
	else:
		raise ValueError(
			"Header payload tidak ditemukan. Kemungkinan: stego-key salah, "
			"video bukan stego yang valid, atau stego-video dibuat dengan codec lossy "
			"(LSB rusak). Gunakan codec lossless saat penyisipan."
		)

	if selected_header.is_random_mode and stego_key is None:
		raise ValueError("Payload menggunakan mode acak. Stego-key wajib diberikan")

	payload_bits_len = selected_header.payload_size * 8
	payload_bits = read_bits_by_mode(
		lsb_stream=lsb_stream,
		mode=selected_mode,
		start_payload_idx=header_bit_len,
		bit_count=payload_bits_len,
		frame_capacity=frame_capacity,
		stego_key=stego_key,
	)
	payload_bytes = bits_to_bytes(payload_bits)

	if selected_header.is_encrypted:
		payload_bytes = A51(a51_key).decrypt(payload_bytes)

	if selected_header.is_file:
		default_name = selected_header.file_name
		if not default_name:
			ext_suffix = f".{selected_header.file_ext}" if selected_header.file_ext else ".bin"
			default_name = f"extracted{ext_suffix}"

		if save_as_path is None:
			os.makedirs(output_dir, exist_ok=True)
			candidate_default = os.path.join(output_dir, default_name)
			if prompt_save_as:
				try:
					typed_path = input(f"Save as: ").strip()
				except EOFError:
					typed_path = ""
				save_as_path = normalize_save_path(typed_path, output_dir, candidate_default)
			else:
				save_as_path = candidate_default
		else:
			save_as_path = normalize_save_path(save_as_path, output_dir, save_as_path)

		parent = os.path.dirname(save_as_path)
		if parent:
			os.makedirs(parent, exist_ok=True)

		with open(save_as_path, "wb") as f:
			f.write(payload_bytes)

		print(f"Ekstraksi berhasil. File disimpan di: {save_as_path}")
		return {
			"type": "file",
			"path": save_as_path,
			"default_name": default_name,
			"encrypted": selected_header.is_encrypted,
			"mode": "random" if selected_header.is_random_mode else "sequential",
		}

	text = payload_bytes.decode("utf-8", errors="replace")
	text_output_path = build_unique_text_path(output_dir, stego_video_path)
	with open(text_output_path, "w", encoding="utf-8") as f:
		f.write(text)

	print("Pesan teks hasil ekstraksi:")
	print(text)
	print(f"Pesan teks disimpan di: {text_output_path}")
	return {
		"type": "text",
		"text": text,
		"path": text_output_path,
		"encrypted": selected_header.is_encrypted,
		"mode": "random" if selected_header.is_random_mode else "sequential",
	}
