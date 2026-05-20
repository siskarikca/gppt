"""
Auto-Buy Telegram Bot - ATMOS VCC ORDER
=========================================
Alur:
1. Kirim "Menu" ke bot
2. Jika bot masih OFF (⛔ order ditutup) → terus retry sampai open
3. Pilih produk nomor 2 (Vcc Gpt)
4. Masukkan jumlah random 5-7
5. Klik "Bayar Sekarang"
6. Jika dapat QR → STOP & kirim notifikasi ke Saved Messages
7. Jika dapat ❌ stok habis → ulangi dari Menu

Requirement:
    pip install telethon

Konfigurasi:
    - Isi API_ID, API_HASH dari https://my.telegram.org
    - Isi BOT_USERNAME dengan username bot target
    - Isi NOTIFY_CHAT_ID untuk menerima notifikasi sukses
"""

import asyncio
import random
import logging
from telethon import TelegramClient, events
from telethon.tl.custom import Button

# ============================
# KONFIGURASI
# ============================
API_ID = 123456                          # Ganti dengan API ID kamu
API_HASH = "your_api_hash_here"          # Ganti dengan API Hash kamu
PHONE_NUMBER = "+62xxxxxxxxxx"           # Ganti dengan nomor telepon kamu
BOT_USERNAME = "AtmosVccOrderBot"        # Username bot target (tanpa @)

# Pengaturan produk
PRODUCT_NUMBER = "2"                     # Nomor produk yang ingin dibeli (Vcc Gpt)
MIN_QTY = 5                              # Jumlah minimum order
MAX_QTY = 7                              # Jumlah maksimum order

# Pengaturan delay (detik)
DELAY_AFTER_MENU = 2                     # Delay setelah kirim Menu
DELAY_AFTER_PRODUCT = 2                  # Delay setelah pilih produk
DELAY_AFTER_QTY = 2                      # Delay setelah kirim jumlah
DELAY_AFTER_BAYAR = 3                    # Delay setelah klik Bayar Sekarang
DELAY_RETRY = 2                          # Delay sebelum retry dari awal
DELAY_ORDER_CLOSED = 10                  # Delay saat order ditutup (polling)

# Pengaturan loop
MAX_RETRY = 0                            # Maksimum retry (0 = unlimited, terus sampai dapat)
SESSION_NAME = "auto_buy_session"        # Nama session file

# Notifikasi - kirim ke chat/user ini saat sukses dapat QR
# Bisa berupa: username ("me" untuk Saved Messages), user_id, atau chat_id
NOTIFY_CHAT_ID = "me"                   # "me" = Saved Messages (kirim ke diri sendiri)

# ============================
# LOGGING
# ============================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("AutoBuy")

# ============================
# STATE MACHINE
# ============================
STATE_IDLE = "idle"
STATE_WAIT_PRODUCT_LIST = "wait_product_list"
STATE_WAIT_PRODUCT_SELECTED = "wait_product_selected"
STATE_WAIT_ORDER_DETAIL = "wait_order_detail"
STATE_WAIT_PAYMENT = "wait_payment"
STATE_ORDER_CLOSED = "order_closed"
STATE_DONE = "done"


class AutoBuyer:
    def __init__(self):
        self.client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
        self.state = STATE_IDLE
        self.retry_count = 0
        self.closed_count = 0
        self.current_qty = 0
        self.bot_entity = None
        self.event_received = asyncio.Event()
        self.last_message = None

    async def start(self):
        """Memulai client dan proses auto-buy."""
        await self.client.start(phone=PHONE_NUMBER)
        log.info("Login berhasil!")

        # Resolve bot entity
        self.bot_entity = await self.client.get_entity(BOT_USERNAME)
        log.info(f"Target bot: @{BOT_USERNAME}")

        # Register handler untuk pesan dari bot
        @self.client.on(events.NewMessage(from_users=self.bot_entity.id))
        async def handler(event):
            await self.handle_bot_response(event)

        # Mulai proses pembelian
        await self.run_buy_loop()

    async def run_buy_loop(self):
        """Loop utama pembelian."""
        while True:
            if MAX_RETRY > 0 and self.retry_count >= MAX_RETRY:
                log.warning(f"Sudah mencapai batas retry ({MAX_RETRY}x). Berhenti.")
                await self.send_notification(
                    "⚠️ AUTO-BUY BERHENTI\n\n"
                    f"Sudah mencapai batas retry ({MAX_RETRY}x).\n"
                    "Stok tidak tersedia."
                )
                break

            try:
                result = await self.execute_buy_flow()

                if result == "success":
                    log.info("=" * 50)
                    log.info("PEMBELIAN BERHASIL! QR Payment diterima.")
                    log.info("=" * 50)

                    # Kirim notifikasi sukses ke Saved Messages
                    await self.send_notification(
                        "✅ SUKSES MENDAPATKAN QR, SILAHKAN BAYAR!\n\n"
                        f"🛒 Produk: #{PRODUCT_NUMBER} (Vcc Gpt)\n"
                        f"📦 Jumlah: {self.current_qty}\n"
                        f"🔄 Retry stok habis: {self.retry_count}x\n"
                        f"🚫 Retry order closed: {self.closed_count}x\n\n"
                        "⏰ Segera lakukan pembayaran sebelum expired!"
                    )

                    log.info("Bot berhenti. Silahkan bayar QR yang diterima.")
                    break

                elif result == "order_closed":
                    self.closed_count += 1
                    log.warning(f"⛔ Order ditutup! Menunggu {DELAY_ORDER_CLOSED}s... (attempt #{self.closed_count})")
                    await asyncio.sleep(DELAY_ORDER_CLOSED)
                    # Tidak menambah retry_count, terus loop sampai open

                elif result == "stock_empty":
                    self.retry_count += 1
                    log.warning(f"❌ Stok habis. Retry ke-{self.retry_count}...")
                    log.info(f"Menunggu {DELAY_RETRY} detik sebelum retry...")
                    await asyncio.sleep(DELAY_RETRY)

                else:
                    # Unknown result, retry
                    self.retry_count += 1
                    log.warning(f"Unknown result. Retry ke-{self.retry_count}...")
                    await asyncio.sleep(DELAY_RETRY)

            except asyncio.TimeoutError:
                self.retry_count += 1
                log.error(f"Timeout! Bot tidak merespon. Retry ke-{self.retry_count}...")
                await asyncio.sleep(DELAY_RETRY)
            except Exception as e:
                self.retry_count += 1
                log.error(f"Error: {e}. Retry ke-{self.retry_count}...")
                await asyncio.sleep(DELAY_RETRY)

        log.info("Auto-buy selesai. Bot dihentikan.")

    async def execute_buy_flow(self) -> str:
        """
        Eksekusi satu flow pembelian.
        Return:
            "success"      - dapat QR pembayaran
            "stock_empty"  - stok habis
            "order_closed" - order sedang ditutup
        """
        # Step 1: Kirim "Menu"
        log.info("─" * 40)
        log.info("Step 1: Mengirim 'Menu'...")
        self.state = STATE_WAIT_PRODUCT_LIST
        self.event_received.clear()
        await self.client.send_message(self.bot_entity, "Menu")
        await asyncio.sleep(DELAY_AFTER_MENU)

        # Tunggu respon list product
        await asyncio.wait_for(self.wait_for_event(), timeout=10)

        # Cek apakah order ditutup
        if self.state == STATE_ORDER_CLOSED:
            return "order_closed"

        # Cek apakah stok habis
        if self.state == STATE_IDLE:
            return "stock_empty"

        # Step 2: Pilih produk nomor 2
        self.current_qty = random.randint(MIN_QTY, MAX_QTY)
        log.info(f"Step 2: Memilih produk nomor {PRODUCT_NUMBER}...")
        self.state = STATE_WAIT_PRODUCT_SELECTED
        self.event_received.clear()
        await self.client.send_message(self.bot_entity, PRODUCT_NUMBER)
        await asyncio.sleep(DELAY_AFTER_PRODUCT)

        # Tunggu respon produk dipilih
        await asyncio.wait_for(self.wait_for_event(), timeout=10)

        # Cek apakah order ditutup atau stok habis
        if self.state == STATE_ORDER_CLOSED:
            return "order_closed"
        if self.state == STATE_IDLE:
            return "stock_empty"

        # Step 3: Masukkan jumlah order (random 5-7)
        log.info(f"Step 3: Memasukkan jumlah order: {self.current_qty}...")
        self.state = STATE_WAIT_ORDER_DETAIL
        self.event_received.clear()
        await self.client.send_message(self.bot_entity, str(self.current_qty))
        await asyncio.sleep(DELAY_AFTER_QTY)

        # Tunggu respon detail order
        await asyncio.wait_for(self.wait_for_event(), timeout=10)

        # Cek apakah stok habis atau order ditutup
        if self.state == STATE_ORDER_CLOSED:
            return "order_closed"
        if self.state == STATE_IDLE:
            return "stock_empty"

        # Step 4: Klik "Bayar Sekarang"
        log.info("Step 4: Mengklik 'Bayar Sekarang'...")
        self.state = STATE_WAIT_PAYMENT
        self.event_received.clear()

        # Coba klik button "Bayar Sekarang"
        clicked = await self.click_button("Bayar Sekarang")
        if not clicked:
            # Fallback: kirim text
            log.warning("Button tidak ditemukan, mengirim text 'Bayar Sekarang'...")
            await self.client.send_message(self.bot_entity, "Bayar Sekarang")

        await asyncio.sleep(DELAY_AFTER_BAYAR)

        # Tunggu respon pembayaran
        await asyncio.wait_for(self.wait_for_event(), timeout=15)

        # Cek hasil
        if self.state == STATE_DONE:
            return "success"
        elif self.state == STATE_ORDER_CLOSED:
            return "order_closed"
        else:
            return "stock_empty"

    async def handle_bot_response(self, event):
        """Handler untuk setiap pesan dari bot."""
        message = event.message
        text = message.text or ""
        self.last_message = message

        log.info(f"Bot response: {text[:100]}...")

        # Cek apakah order sedang ditutup
        if "⛔" in text or "order sedang ditutup" in text.lower() or "tunggu sampai open" in text.lower():
            log.warning("Detected: ORDER DITUTUP! ⛔")
            self.state = STATE_ORDER_CLOSED
            self.event_received.set()
            return

        # Cek apakah stok habis (semua variasi respon)
        if ("❌" in text or "stok baru saja habis" in text.lower() or
                "Stok tidak cukup" in text or "stok produk ini habis" in text.lower() or
                "stok habis" in text.lower() or "out of stock" in text.lower()):
            log.warning("Detected: STOK HABIS!")
            self.state = STATE_IDLE
            self.event_received.set()
            return

        # Cek berdasarkan state
        if self.state == STATE_WAIT_PRODUCT_LIST:
            if "LIST PRODUCT" in text or "Silakan pilih nomor produk" in text.lower() or "pilih nomor produk" in text.lower():
                log.info("Received: List product")
                self.event_received.set()

        elif self.state == STATE_WAIT_PRODUCT_SELECTED:
            if "PRODUK DIPILIH" in text or "Masukkan jumlah order" in text:
                log.info("Received: Produk dipilih")
                self.event_received.set()
            elif "stok" in text.lower() and "habis" in text.lower():
                log.warning("Stok habis saat pilih produk!")
                self.state = STATE_IDLE
                self.event_received.set()

        elif self.state == STATE_WAIT_ORDER_DETAIL:
            if "DETAIL ORDER" in text or "Bayar Sekarang" in text:
                log.info("Received: Detail order")
                self.state = STATE_WAIT_ORDER_DETAIL
                self.event_received.set()

        elif self.state == STATE_WAIT_PAYMENT:
            # Cek apakah ini QR code / invoice pembayaran
            if message.photo or message.media or "bayar" in text.lower() or "qr" in text.lower() or "invoice" in text.lower() or "pembayaran" in text.lower() or "transfer" in text.lower():
                log.info("Received: PAYMENT QR/Invoice!")
                log.info(f"Payment info: {text}")
                self.state = STATE_DONE
                self.event_received.set()
            elif "❌" in text or "stok" in text.lower():
                log.warning("Stok habis saat pembayaran!")
                self.state = STATE_IDLE
                self.event_received.set()
            else:
                # Anggap sebagai respon payment juga
                log.info("Received: Payment response (unknown format)")
                log.info(f"Content: {text}")
                self.state = STATE_DONE
                self.event_received.set()

    async def click_button(self, button_text: str) -> bool:
        """Coba klik inline button dengan text tertentu."""
        if self.last_message and self.last_message.buttons:
            for row in self.last_message.buttons:
                for button in row:
                    if button.text and button_text.lower() in button.text.lower():
                        try:
                            await button.click()
                            log.info(f"Button '{button.text}' clicked!")
                            return True
                        except Exception as e:
                            log.error(f"Error clicking button: {e}")
                            return False
        return False

    async def send_notification(self, message: str):
        """Kirim notifikasi ke Saved Messages."""
        try:
            await self.client.send_message(NOTIFY_CHAT_ID, message)
            log.info(f"Notifikasi terkirim ke: {NOTIFY_CHAT_ID}")
        except Exception as e:
            log.error(f"Gagal kirim notifikasi: {e}")
            # Fallback: print ke terminal
            print("\n" + "!" * 50)
            print(message)
            print("!" * 50 + "\n")

    async def wait_for_event(self):
        """Tunggu event dari bot."""
        await self.event_received.wait()
        self.event_received.clear()


async def main():
    print("=" * 50)
    print("   AUTO-BUY TELEGRAM - ATMOS VCC ORDER")
    print("=" * 50)
    print(f"   Target Bot  : @{BOT_USERNAME}")
    print(f"   Produk      : #{PRODUCT_NUMBER} (Vcc Gpt)")
    print(f"   Jumlah      : {MIN_QTY}-{MAX_QTY} (random)")
    print(f"   Max Retry   : {'Unlimited' if MAX_RETRY == 0 else MAX_RETRY}")
    print(f"   Notify      : {NOTIFY_CHAT_ID}")
    print("=" * 50)
    print()
    print("   ⛔ Order ditutup → Terus polling sampai open")
    print("   ❌ Stok habis    → Retry dari Menu")
    print("   ✅ Dapat QR      → Stop & notif Saved Messages")
    print("=" * 50)
    print()

    buyer = AutoBuyer()
    await buyer.start()


if __name__ == "__main__":
    asyncio.run(main())
