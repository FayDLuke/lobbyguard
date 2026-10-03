# endstone-lobby-protect

Plugin Python untuk Endstone 0.11.x.

## Set area lobby
Berdiri di sudut pertama lalu `/lobbyprotect pos1`, pindah ke sudut seberangnya lalu `/lobbyprotect pos2`.
Hanya X dan Z yang dipakai, Y diabaikan, jadi proteksi berlaku dari dasar sampai atas dunia.
Command lain: `/lobbyprotect info`, `/lobbyprotect clear`, `/lobbyprotect reload` (alias `/lp`).

## Portal (ala Hypixel hub)
1. `/portal set [nama]` lalu break block pojok 1 dan block pojok 2 (block tidak pecah). Ukuran portal = kotak antara dua block itu, termasuk Y.
2. `/portal addcmd rtp` untuk menambah command yang dijalankan saat pemain masuk portal (boleh beberapa kali).
   Awalan `console:` menjalankan lewat console, `{player}` diganti nama pemain.
3. Lainnya: `/portal list`, `/portal select <nama>`, `/portal clearcmd`, `/portal remove <nama>`, `/portal cancel`.

## Fitur
0. Pemain juga tidak bisa place block di lobby
1. Pemain tidak bisa break block di area lobby (OP bisa bypass lewat permission `lobby_protect.bypass`, bisa dimatikan di config)
2. Semua mob tidak spawn di area lobby (ada whitelist untuk NPC / armor stand)
3. Pemain di area lobby yang Y-nya di bawah `below-y` (default 250) otomatis di-teleport ke koordinat di `config.toml`

## Build & install
```
pip install build
python -m build --wheel
```
Copy file `dist/endstone_lobby_protect-1.2.0-py3-none-any.whl` ke folder `plugins/` server Endstone.
Config otomatis dibuat di `plugins/lobby_protect/config.toml`. Reload: `/lobbyprotect reload`.
