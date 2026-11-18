# -*- coding: utf-8 -*-
"""
buat_pengguna.py -- membuat pengguna baru, atau mengatur ulang password pengguna yang sudah ada (mis. lupa password).

    python buat_pengguna.py                       (menanyakan username dan password)
    python buat_pengguna.py operator1             (menanyakan password)
    python buat_pengguna.py operator1 sandi-baru  (langsung; sandi tampil di riwayat terminal, hati-hati)

Aman dijalankan saat aplikasi sedang hidup.
"""

import getpass
import sys

from app import create_app
from services import auth


def main() -> int:
    username = sys.argv[1].strip() if len(sys.argv) > 1 else input("Username: ").strip()
    password = sys.argv[2] if len(sys.argv) > 2 else None
    if not username:
        print("Username tidak boleh kosong.")
        return 2
    if password is None:
        password = getpass.getpass("Password baru (minimal 6 karakter): ")
        if password != getpass.getpass("Ulangi password: "):
            print("Dua isian password tidak sama. Tidak ada yang diubah.")
            return 2

    app = create_app()
    with app.app_context():
        try:
            if auth.atur_password_pengguna(username, password):
                auth.reset_percobaan_login(username)
                print(f"Password pengguna '{username}' berhasil diatur ulang.")
            else:
                auth.buat_pengguna(username, password)
                print(f"Pengguna '{username}' berhasil dibuat.")
        except ValueError as exc:
            print("Gagal:", exc)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
