import os
import sys

from src.insertion import insert_message_to_video
from src.extraction import extract_message_from_video

base_dir = os.path.dirname(os.path.abspath(__file__))
output_video_dir = os.path.join(base_dir, "output_video")
output_message_dir = os.path.join(base_dir, "output_pesan")
os.makedirs(output_video_dir, exist_ok=True)
os.makedirs(output_message_dir, exist_ok=True)

print("=== Program Steganografi Video AVI ===")
print("1. Sisipkan pesan")
print("2. Extract pesan")

pilihan = input("Pilih menu (1/2): ").strip()

if pilihan == "1":
    video_path = os.path.join(base_dir, "video", "contoh_vid.avi")

    secret_text = input("Ketik pesan rahasia: ").strip()
    if not secret_text:
        print("Pesan rahasia kosong. Proses dibatalkan.")
        sys.exit(0)

    video_name = os.path.splitext(os.path.basename(video_path))[0]
    output_path = os.path.join(output_video_dir, f"{video_name}_stego.avi")

    temp_secret_path = os.path.join(output_video_dir, "temp_secret_message.txt")
    with open(temp_secret_path, "w", encoding="utf-8") as f:
        f.write(secret_text)

    while True:
        answer = input("Gunakan enkripsi A5/1? (y/n): ").strip().lower()
        if answer in {"y", "yes", "ya"}:
            encrypt_payload = True
            break
        if answer in {"n", "no", "tidak"}:
            encrypt_payload = False
            break
        print("Input tidak valid. Masukkan y/n.")

    a51_key = None
    if encrypt_payload:
        a51_key = input("Masukkan kunci A5/1 (string): ").strip()
        if a51_key is None:
            a51_key = ""

    while True:
        mode = input("Mode penyisipan (sequential/random): ").strip().lower()
        if mode in {"sequential", "random"}:
            break
        print("Mode tidak valid. Pilih 'sequential' atau 'random'.")

    stego_key = None
    if mode == "random":
        stego_key = input("Masukkan stego-key (string): ").strip()
        if stego_key is None:
            stego_key = ""

    insert_message_to_video(
        video_path=video_path,
        secret_path=temp_secret_path,
        output_path=output_path,
        encrypt_payload=encrypt_payload,
        a51_key=a51_key,
        mode=mode,
        stego_key=stego_key,
    )

    if os.path.isfile(temp_secret_path):
        os.remove(temp_secret_path)

    print(f"Stego-video tersimpan di: {output_path}")

elif pilihan == "2":
    stego_name = input("Nama file stego yang ingin diextract: ").strip()
    if not stego_name:
        print("Nama file stego kosong. Proses dibatalkan.")
        sys.exit(0)

    stego_name = os.path.basename(stego_name)
    stego_video_path = os.path.join(output_video_dir, stego_name)

    if not os.path.isfile(stego_video_path):
        print(f"Stego-video tidak ditemukan: {stego_video_path}")
        sys.exit(0)

    while True:
        encrypted_answer = input("Apakah payload terenkripsi A5/1? (y/n): ").strip().lower()
        if encrypted_answer in {"y", "yes", "ya"}:
            encrypted_payload = True
            break
        if encrypted_answer in {"n", "no", "tidak"}:
            encrypted_payload = False
            break
        print("Input tidak valid. Masukkan y/n.")

    a51_key = None
    if encrypted_payload:
        a51_key = input("Masukkan kunci A5/1 (string): ").strip()

    while True:
        random_answer = input("Apakah penyisipan mode random? (y/n): ").strip().lower()
        if random_answer in {"y", "yes", "ya"}:
            random_mode = True
            break
        if random_answer in {"n", "no", "tidak"}:
            random_mode = False
            break
        print("Input tidak valid. Masukkan y/n.")

    stego_key = None
    if random_mode:
        stego_key = input("Masukkan stego-key (string): ").strip()

    extract_message_from_video(
        stego_video_path=stego_video_path,
        a51_key=a51_key,
        stego_key=stego_key,
        output_dir=output_message_dir,
        prompt_save_as=True,
    )

else:
    print("Pilihan menu tidak valid. Gunakan 1 atau 2.")
