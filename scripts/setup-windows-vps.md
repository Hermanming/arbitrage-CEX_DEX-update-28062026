# Setup Arbitrage Bot di Windows VPS (Singapore)

Panduan lengkap deploy bot ke **VPS Windows** di region yang **tidak diblokir Binance** (Singapore, Tokyo, Frankfurt, dll).

> ✅ Disarankan: VPS Windows Server 2019/2022, RAM min 2GB, disk 20GB, dengan public IP statis.

---

## 1. Install Prasyarat

### 1.1 Python 3.11+
- Download: https://www.python.org/downloads/windows/
- ✅ Saat install, **centang "Add Python to PATH"**.
- Verify:
  ```cmd
  python --version
  pip --version
  ```

### 1.2 Node.js 20 LTS + Yarn
- Node: https://nodejs.org/en/download
- Setelah node terinstall, buka **CMD as Administrator**:
  ```cmd
  npm install -g yarn
  yarn --version
  ```

### 1.3 MongoDB Community Server
- Download: https://www.mongodb.com/try/download/community
- Pilih: **Windows x64 MSI** + **Install MongoDB as a Service** (centang)
- Verify (PowerShell):
  ```powershell
  Get-Service MongoDB
  # Status: Running
  ```

> 💡 **Alternatif tanpa install**: pakai **MongoDB Atlas** (cloud free tier). Daftar di https://www.mongodb.com/cloud/atlas, buat cluster M0 free, dapatkan connection string mongodb+srv://...

### 1.4 Git for Windows
- Download: https://git-scm.com/download/win
- Default install OK.
- Verify:
  ```cmd
  git --version
  ```

### 1.5 NSSM (Non-Sucking Service Manager)
Untuk menjalankan bot sebagai Windows Service (auto-start saat boot, auto-restart kalau crash).
- Download: https://nssm.cc/download
- Extract `nssm-2.24.zip`, ambil `win64\nssm.exe`
- Pindahkan ke `C:\Windows\System32\` (supaya selalu di PATH)
- Verify:
  ```cmd
  nssm --version
  ```

---

## 2. Clone Project dari GitHub

```cmd
cd C:\
git clone https://github.com/<your-username>/<repo-name>.git arbitrage-bot
cd arbitrage-bot
```

---

## 3. Setup Backend

```cmd
cd C:\arbitrage-bot\backend

REM Buat virtual environment
python -m venv venv

REM Activate venv
venv\Scripts\activate

REM Install dependencies
pip install -r requirements.txt

REM Copy & edit .env
copy env.example.txt .env
notepad .env
```

**Edit `.env`** dengan nilai:

```env
MONGO_URL=mongodb://localhost:27017
DB_NAME=arbitrage_bot
CORS_ORIGINS=*
FERNET_KEY=<generate-baru-pakai-perintah-di-bawah>
SOLANA_RPC=https://api.mainnet-beta.solana.com
```

**Generate FERNET_KEY:**
```cmd
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Copy outputnya ke `FERNET_KEY=` di `.env`. **Simpan juga di password manager** — jika hilang, data terenkripsi di MongoDB tidak bisa di-decrypt.

**Test backend manual:**
```cmd
python -m uvicorn server:app --host 0.0.0.0 --port 8001
```
Buka http://localhost:8001/docs → harusnya muncul Swagger UI. Tekan `Ctrl+C` untuk stop.

---

## 4. Setup Frontend

Buka CMD baru:

```cmd
cd C:\arbitrage-bot\frontend

REM Install dependencies
yarn install

REM Copy & edit .env
copy env.example.txt .env
notepad .env
```

**Edit `.env`:**
```env
REACT_APP_BACKEND_URL=http://<your-vps-public-ip>:8001
WDS_SOCKET_PORT=443
```
(Ganti `<your-vps-public-ip>` dengan IP public VPS Singapore Anda.)

**Build production:**
```cmd
yarn build
```
Output ada di `frontend\build`.

**Test serve:**
```cmd
yarn global add serve
serve -s build -l 3000
```
Buka http://<your-vps-public-ip>:3000 — harus muncul dashboard.

---

## 5. Buka Firewall Port

Di PowerShell **as Administrator**:

```powershell
New-NetFirewallRule -DisplayName "Arbitrage Backend" -Direction Inbound -LocalPort 8001 -Protocol TCP -Action Allow
New-NetFirewallRule -DisplayName "Arbitrage Frontend" -Direction Inbound -LocalPort 3000 -Protocol TCP -Action Allow
```

Cek di Digitalku panel: pastikan **inbound 8001 & 3000** juga dibuka di firewall provider.

---

## 6. Install sebagai Windows Service (Auto-Start)

Pakai helper script:

```cmd
cd C:\arbitrage-bot\scripts

REM Right-click install-services.bat -> Run as Administrator
install-services.bat
```

Script akan:
- Register service `ArbitrageBackend` (uvicorn FastAPI port 8001)
- Register service `ArbitrageFrontend` (serve port 3000)
- Set keduanya auto-start saat Windows boot
- Setup log rotation di backend (`backend.out.log`, `backend.err.log`)

**Verify:**
```cmd
nssm status ArbitrageBackend
nssm status ArbitrageFrontend
```
Atau buka `services.msc` → cari "ArbitrageBackend" & "ArbitrageFrontend" → status Running.

**Manage services:**
```cmd
nssm start    ArbitrageBackend
nssm stop     ArbitrageBackend
nssm restart  ArbitrageBackend
nssm remove   ArbitrageBackend confirm
```

---

## 7. Cek Logs

Log file otomatis tersimpan di:
- `C:\arbitrage-bot\backend\backend.out.log` (stdout)
- `C:\arbitrage-bot\backend\backend.err.log` (errors)
- `C:\arbitrage-bot\frontend\frontend.out.log`
- `C:\arbitrage-bot\frontend\frontend.err.log`

**Live tail (PowerShell):**
```powershell
Get-Content C:\arbitrage-bot\backend\backend.err.log -Wait -Tail 50
```

---

## 8. Setup Bot via UI

1. Buka `http://<your-vps-public-ip>:3000` dari laptop Anda.
2. Klik **Settings** di header.
3. Isi keys (semua opsional untuk paper mode):
   - **Binance API Key + Secret** (untuk live mode)
   - **Phantom Private Key Base58** (untuk live DEX swap)
   - **Telegram Bot Token + Chat ID** (untuk notifikasi)
4. Atur **Risk Caps** & **Coin Universe**.
5. Klik **Save Configuration**.
6. Toggle ke **LIVE** di header saat siap.

---

## 9. Update Bot ke Versi Terbaru

```cmd
cd C:\arbitrage-bot

REM Stop services
nssm stop ArbitrageBackend
nssm stop ArbitrageFrontend

REM Pull update
git pull

REM Update backend deps
cd backend
venv\Scripts\activate
pip install -r requirements.txt
deactivate
cd ..

REM Rebuild frontend
cd frontend
yarn install
yarn build
cd ..

REM Start services
nssm start ArbitrageBackend
nssm start ArbitrageFrontend
```

---

## 10. Troubleshooting

| Gejala | Solusi |
|---|---|
| Service tidak start | Cek `backend.err.log`. Common: `.env` salah path, Mongo belum jalan, FERNET_KEY tidak valid. |
| Dashboard muncul tapi data kosong | Cek `REACT_APP_BACKEND_URL` di `frontend\.env` — harus pakai IP/domain yang accessible dari browser. Frontend perlu di-`yarn build` ulang setelah ubah env. |
| `data-stream.binance.vision` connect tapi `api.binance.com` HTTP 451 | Berarti VPS region masih diblokir Binance untuk private endpoint. Pindah ke Singapore/Tokyo/Frankfurt. |
| Telegram tidak terima notif | Cek Bot Token + Chat ID, lalu test via tombol "Test Telegram" di Settings. Pastikan Anda sudah `/start` ke bot Anda. |
| WS sering disconnect | Network issue. Cek firewall VPS, atau coba alternative endpoint (`wss://stream.binance.com:9443`). |
| MongoDB error `Authentication failed` | Kalau pakai Atlas, pastikan IP VPS di-whitelist di Network Access. |

---

## 11. Backup MongoDB (Recommended Weekly)

```cmd
REM Backup ke folder C:\backups
mkdir C:\backups
"C:\Program Files\MongoDB\Server\7.0\bin\mongodump.exe" --uri="mongodb://localhost:27017/arbitrage_bot" --out=C:\backups\%date:~-4,4%%date:~-10,2%%date:~-7,2%
```

Restore:
```cmd
"C:\Program Files\MongoDB\Server\7.0\bin\mongorestore.exe" --uri="mongodb://localhost:27017/arbitrage_bot" C:\backups\20260301\arbitrage_bot
```

---

## ✅ Checklist Final

- [ ] Python, Node, Yarn, MongoDB, Git, NSSM terinstall
- [ ] Repo di-clone ke `C:\arbitrage-bot`
- [ ] `backend\.env` & `frontend\.env` sudah di-edit
- [ ] `FERNET_KEY` di-backup di password manager
- [ ] `yarn build` sukses
- [ ] Firewall port 8001 & 3000 open (Windows + Digitalku panel)
- [ ] `install-services.bat` jalan as Admin, kedua service status Running
- [ ] Dashboard accessible di browser dari laptop
- [ ] WS Live indicator menyala 🟢
- [ ] Paper trade berhasil sebelum coba LIVE mode

Selamat trading! 🚀
