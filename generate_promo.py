import sys

# ============================
# KONFIGURASI
# ============================
OUTPUT_FILE = "promo_codes.txt"  # File untuk menyimpan promo code
CODE_LENGTH = 16                 # Panjang promo code (16 karakter)

# Urutan karakter: A-Z lalu 0-9
CHARACTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
BASE = len(CHARACTERS)  # 36


def load_existing_codes() -> set:
    """
    Baca promo code yang sudah ada di file txt untuk cek duplikat.
    """
    existing = set()
    try:
        with open(OUTPUT_FILE, "r") as f:
            for line in f:
                code = line.strip()
                if code:
                    existing.add(code)
    except FileNotFoundError:
        pass
    return existing


def code_to_number(code: str) -> int:
    """
    Konversi promo code ke angka (base-36 dengan urutan A-Z, 0-9).
    """
    number = 0
    for char in code:
        index = CHARACTERS.index(char)
        number = number * BASE + index
    return number


def number_to_code(number: int) -> str:
    """
    Konversi angka ke promo code (base-36 dengan urutan A-Z, 0-9).
    """
    if number == 0:
        return CHARACTERS[0] * CODE_LENGTH

    chars = []
    while number > 0:
        chars.append(CHARACTERS[number % BASE])
        number //= BASE

    # Pad dengan karakter pertama (A) jika kurang dari 16 karakter
    while len(chars) < CODE_LENGTH:
        chars.append(CHARACTERS[0])

    return ''.join(reversed(chars))


def get_last_code(existing_codes: set) -> int:
    """
    Cari nomor urut terakhir dari promo code yang sudah ada.
    """
    if not existing_codes:
        return -1

    max_number = -1
    for code in existing_codes:
        if len(code) == CODE_LENGTH and all(c in CHARACTERS for c in code):
            num = code_to_number(code)
            if num > max_number:
                max_number = num
    return max_number


def generate_promo_codes(jumlah: int) -> list:
    """
    Generate promo code secara berurutan, tanpa duplikat.
    """
    existing_codes = load_existing_codes()
    print(f"Promo code yang sudah ada di '{OUTPUT_FILE}': {len(existing_codes)}")
    print("-" * 50)

    # Mulai dari nomor urut setelah yang terakhir
    last_number = get_last_code(existing_codes)
    current_number = last_number + 1

    new_codes = []

    while len(new_codes) < jumlah:
        code = number_to_code(current_number)

        # Cek duplikat (seharusnya tidak terjadi karena sequential, tapi untuk safety)
        if code not in existing_codes:
            new_codes.append(code)
            existing_codes.add(code)

        current_number += 1

    return new_codes


def save_codes(new_codes: list):
    """
    Simpan promo code baru ke file (append, tidak menimpa yang lama).
    """
    with open(OUTPUT_FILE, "a") as f:
        for code in new_codes:
            f.write(code + "\n")


def main():
    if len(sys.argv) < 2:
        print("Usage: python generate_promo.py <JUMLAH>")
        print("")
        print("Contoh:")
        print("  python generate_promo.py 10     # Generate 10 promo code")
        print("  python generate_promo.py 100    # Generate 100 promo code")
        print("  python generate_promo.py 1000   # Generate 1000 promo code")
        sys.exit(1)

    try:
        jumlah = int(sys.argv[1])
    except ValueError:
        print("[ERROR] Jumlah harus berupa angka!")
        sys.exit(1)

    if jumlah <= 0:
        print("[ERROR] Jumlah harus lebih dari 0!")
        sys.exit(1)

    print(f"Generating {jumlah} promo code (sequential)...")
    print("=" * 50)

    new_codes = generate_promo_codes(jumlah)

    # Tampilkan promo code yang baru digenerate
    print(f"\n{len(new_codes)} promo code baru:")
    print("-" * 50)
    for code in new_codes:
        print(code)

    # Simpan ke file
    save_codes(new_codes)

    print("\n" + "=" * 50)
    print(f"Berhasil generate {len(new_codes)} promo code baru!")
    print(f"Disimpan ke '{OUTPUT_FILE}' (append, tidak menimpa yang lama)")

    # Hitung total
    total = load_existing_codes()
    print(f"Total promo code di file: {len(total)}")


if __name__ == "__main__":
    main()
