"""
Multi-Account Auto-Buy Telegram Bot - ATMOS VCC ORDER
=======================================================
Menjalankan 5 akun sekaligus dalam 1 process (asyncio concurrent).
Lebih hemat RAM dan mudah dikelola.

Alur per akun:
1. Kirim "Menu" ke bot
2. Jika bot OFF (⛔ order ditutup) → terus retry sampai open
3. Pilih produk nomor 2 (Vcc Gpt)
4. Masukkan jumlah random 5-7
5. Klik "Bayar Sekarang"
6. Jika dapat QR → STOP akun ini & kirim notifikasi ke Saved Messages
7. Jika dapat ❌ stok habis → ulangi dari Menu

Requirement:
    pip install telethon

Jalankan:
    python multi_auto_buy.py
"""

import asyncio
import random
import logging
from telethon import TelegramClient, events

# ============================
# KONFIGURASI AKUN
# ============================
ACCOUNTS = [
    {
        "name": "braygmail",
        "api_id": 22398981,
        "api_hash": "00ec33387df2b115ecff356611e145d0",
        "phone": "+6283193003189",
        "session": "braygmail",
    },
    {
        "name": "china",
        "api_id": 33193772,
        "api_hash": "d8c8af5aae0c036c65e1db573e1a538c",
        "phone": "+6283152487117",
        "session": "china",
    },
    {
        "name": "iltid",
        "api_id": 25775833,
        "api_hash": "e36b0aa381daae3cb2bf6818e0d8f615",
        "phone": "+6287732484716",
        "session": "iltid",
    },
    {
        "name": "meli",
        "api_id": 32184483,
        "api_hash": "a143d96f5cf657cac88c183d84a7a880",
        "phone": "+6289507951099",
        "session": "meli",
    },
    {
        "name": "saka",
        "api_id": 33388614,
        "api_hash": "8de7037c2d84aded1d87a5a063f98f86",
        "phone": "+6283163555901",
        "session": "saka",
    },
]

# ============================
# KONFIGURASI GLOBAL
# ============================
BOT_USERNAME = "atmosvcc_bot"            # Username bot target (tanpa @)
PRODUCT_NUMBER = "2"                     # Nomor produk yang ingin dibeli (Vcc Gpt)
MIN_QTY = 5                              # Jumlah minimum order
MAX_QTY = 7                              # Jumlah maksimum order

# Pengaturan delay (detik)
DELAY_AFTER_MENU = 5                     # Delay setelah kirim Menu
DELAY_AFTER_PRODUCT = 2                  # Delay setelah pilih produk
DELAY_AFTER_QTY = 2                      # Delay setelah kirim jumlah
DELAY_AFTER_BAYAR = 3                    # Delay setelah klik Bayar Sekarang
DELAY_RETRY = 2                          # Delay sebelum retry dari awal
DELAY_ORDER_CLOSED = 5                   # Delay saat order ditutup (polling)
STAGGER_DELAY = 2                        # Delay antar akun saat start (anti-flood)

# Pengaturan loop
MAX_RETRY = 0                            # Maksimum retry (0 = unlimited)
NOTIFY_CHAT_ID = "me"                    # Notifikasi ke Saved Messages

# ============================
# LOGGING
# ============================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S"
)

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


class AccountBuyer:
    """Auto-buyer untuk satu akun."""

    def __init__(self, account: dict):
        self.account = account
        self.name = account["name"]
        self.log = logging.getLogger(self.name)
        self.client = TelegramClient(
            account["session"],
            account["api_id"],
            account["api_hash"]
        )
        self.state = STATE_IDLE
        self.retry_count = 0
        self.closed_count = 0
        self.current_qty = 0
        self.bot_entity = None
        self.event_received = asyncio.Event()
        self.last_message = None
        self.is_done = False

    async def start(self):
        """Memulai client dan proses auto-buy."""
        try:
            await self.client.start(phone=self.account["phone"])
            self.log.info("✅ Login berhasil!")

            # Resolve bot entity
            self.bot_entity = await self.client.get_entity(BOT_USERNAME)
            self.log.info(f"Target bot: @{BOT_USERNAME}")

            # Register handler untuk pesan dari bot
            @self.client.on(events.NewMessage(from_users=self.bot_entity.id))
            async def handler(event):
                await self.handle_bot_response(event)

            # Mulai proses pembelian
            await self.run_buy_loop()

        except Exception as e:
            self.log.error(f"❌ Gagal login: {e}")
            self.is_done = True

    async def run_buy_loop(self):
        """Loop utama pembelian."""
        while True:
            if MAX_RETRY > 0 and self.retry_count >= MAX_RETRY:
                self.log.warning(f"Batas retry ({MAX_RETRY}x). Berhenti.")
                await self.send_notification(
                    f"⚠️ [{self.name.upper()}] AUTO-BUY BERHENTI\n\n"
                    f"Sudah mencapai batas retry ({MAX_RETRY}x).\n"
                    "Stok tidak tersedia."
                )
                break

            try:
                result = await self.execute_buy_flow()

                if result == "success":
                    self.log.info("=" * 40)
                    self.log.info("🎉 QR Payment diterima!")
                    self.log.info("=" * 40)

                    await self.send_notification(
                        f"✅ [{self.name.upper()}] SUKSES MENDAPATKAN QR!\n"
                        f"SILAHKAN BAYAR!\n\n"
                        f"🛒 Produk: #{PRODUCT_NUMBER} (Vcc Gpt)\n"
                        f"📦 Jumlah: {self.current_qty}\n"
                        f"🔄 Retry stok habis: {self.retry_count}x\n"
                        f"🚫 Retry order closed: {self.closed_count}x\n\n"
                        "⏰ Segera lakukan pembayaran sebelum expired!"
                    )
                    break

                elif result == "order_closed":
                    self.closed_count += 1
                    self.log.warning(f"⛔ Order ditutup! (#{self.closed_count})")
                    await asyncio.sleep(DELAY_ORDER_CLOSED)

                elif result == "stock_empty":
                    self.retry_count += 1
                    self.log.warning(f"❌ Stok habis. Retry #{self.retry_count}")
                    await asyncio.sleep(DELAY_RETRY)

                else:
                    self.retry_count += 1
                    self.log.warning(f"Unknown. Retry #{self.retry_count}")
                    await asyncio.sleep(DELAY_RETRY)

            except asyncio.TimeoutError:
                self.retry_count += 1
                self.log.error(f"Timeout! Retry #{self.retry_count}")
                await asyncio.sleep(DELAY_RETRY)
            except Exception as e:
                self.retry_count += 1
                self.log.error(f"Error: {e}. Retry #{self.retry_count}")
                await asyncio.sleep(DELAY_RETRY)

        self.is_done = True
        self.log.info("Selesai.")

    async def execute_buy_flow(self) -> str:
        """Eksekusi satu flow pembelian."""
        # Step 1: Kirim "Menu"
        self.log.info("→ Menu")
        self.state = STATE_WAIT_PRODUCT_LIST
        self.event_received.clear()
        await self.client.send_message(self.bot_entity, "Menu")
        await asyncio.sleep(DELAY_AFTER_MENU)

        await asyncio.wait_for(self.wait_for_event(), timeout=10)

        if self.state == STATE_ORDER_CLOSED:
            return "order_closed"
        if self.state == STATE_IDLE:
            return "stock_empty"

        # Step 2: Pilih produk
        self.current_qty = random.randint(MIN_QTY, MAX_QTY)
        self.log.info(f"→ Produk {PRODUCT_NUMBER}")
        self.state = STATE_WAIT_PRODUCT_SELECTED
        self.event_received.clear()
        await self.client.send_message(self.bot_entity, PRODUCT_NUMBER)
        await asyncio.sleep(DELAY_AFTER_PRODUCT)

        await asyncio.wait_for(self.wait_for_event(), timeout=10)

        if self.state == STATE_ORDER_CLOSED:
            return "order_closed"
        if self.state == STATE_IDLE:
            return "stock_empty"

        # Step 3: Masukkan jumlah
        self.log.info(f"→ Qty: {self.current_qty}")
        self.state = STATE_WAIT_ORDER_DETAIL
        self.event_received.clear()
        await self.client.send_message(self.bot_entity, str(self.current_qty))
        await asyncio.sleep(DELAY_AFTER_QTY)

        await asyncio.wait_for(self.wait_for_event(), timeout=10)

        if self.state == STATE_ORDER_CLOSED:
            return "order_closed"
        if self.state == STATE_IDLE:
            return "stock_empty"

        # Step 4: Bayar Sekarang
        self.log.info("→ Bayar Sekarang")
        self.state = STATE_WAIT_PAYMENT
        self.event_received.clear()

        clicked = await self.click_button("Bayar Sekarang")
        if not clicked:
            await self.client.send_message(self.bot_entity, "Bayar Sekarang")

        await asyncio.sleep(DELAY_AFTER_BAYAR)

        await asyncio.wait_for(self.wait_for_event(), timeout=15)

        if self.state == STATE_DONE:
            return "success"
        elif self.state == STATE_ORDER_CLOSED:
            return "order_closed"
        else:
            return "stock_empty"

    async def handle_bot_response(self, event):
        """Handler untuk pesan dari bot."""
        message = event.message
        text = message.text or ""
        self.last_message = message

        # Cek order ditutup
        if "⛔" in text or "order sedang ditutup" in text.lower() or "tunggu sampai open" in text.lower():
            self.state = STATE_ORDER_CLOSED
            self.event_received.set()
            return

        # Cek stok habis (semua variasi)
        if ("❌" in text or "stok baru saja habis" in text.lower() or
                "Stok tidak cukup" in text or "stok produk ini habis" in text.lower() or
                "stok habis" in text.lower() or "out of stock" in text.lower()):
            self.state = STATE_IDLE
            self.event_received.set()
            return

        # Cek berdasarkan state
        if self.state == STATE_WAIT_PRODUCT_LIST:
            if "LIST PRODUCT" in text or "pilih nomor produk" in text.lower():
                self.event_received.set()

        elif self.state == STATE_WAIT_PRODUCT_SELECTED:
            if "PRODUK DIPILIH" in text or "Masukkan jumlah order" in text:
                self.event_received.set()
            elif "stok" in text.lower() and "habis" in text.lower():
                self.state = STATE_IDLE
                self.event_received.set()

        elif self.state == STATE_WAIT_ORDER_DETAIL:
            if "DETAIL ORDER" in text or "Bayar Sekarang" in text:
                self.event_received.set()

        elif self.state == STATE_WAIT_PAYMENT:
            if message.photo or message.media or "qr" in text.lower() or "invoice" in text.lower() or "pembayaran" in text.lower() or "transfer" in text.lower():
                self.state = STATE_DONE
                self.event_received.set()
            elif "❌" in text or "stok" in text.lower():
                self.state = STATE_IDLE
                self.event_received.set()
            else:
                self.state = STATE_DONE
                self.event_received.set()

    async def click_button(self, button_text: str) -> bool:
        """Coba klik inline button."""
        if self.last_message and self.last_message.buttons:
            for row in self.last_message.buttons:
                for button in row:
                    if button.text and button_text.lower() in button.text.lower():
                        try:
                            await button.click()
                            return True
                        except:
                            return False
        return False

    async def send_notification(self, message: str):
        """Kirim notifikasi ke Saved Messages."""
        try:
            await self.client.send_message(NOTIFY_CHAT_ID, message)
            self.log.info("📨 Notifikasi terkirim")
        except Exception as e:
            self.log.error(f"Gagal kirim notifikasi: {e}")
            print(f"\n{'!'*50}\n{message}\n{'!'*50}\n")

    async def wait_for_event(self):
        """Tunggu event dari bot."""
        await self.event_received.wait()
        self.event_received.clear()


async def run_account(account: dict, delay: float):
    """Jalankan satu akun dengan stagger delay."""
    await asyncio.sleep(delay)
    buyer = AccountBuyer(account)
    await buyer.start()
    return buyer


async def main():
    print("=" * 60)
    print("   MULTI-ACCOUNT AUTO-BUY - ATMOS VCC ORDER")
    print("   5 Akun dalam 1 Process (Concurrent)")
    print("=" * 60)
    print(f"   Target Bot  : @{BOT_USERNAME}")
    print(f"   Produk      : #{PRODUCT_NUMBER} (Vcc Gpt)")
    print(f"   Jumlah      : {MIN_QTY}-{MAX_QTY} (random)")
    print(f"   Max Retry   : {'Unlimited' if MAX_RETRY == 0 else MAX_RETRY}")
    print(f"   Akun        : {len(ACCOUNTS)} akun")
    print("=" * 60)
    print()
    for i, acc in enumerate(ACCOUNTS):
        print(f"   [{i+1}] {acc['name']:12s} | {acc['phone']}")
    print()
    print("=" * 60)
    print("   ⛔ Order ditutup → Terus polling sampai open")
    print("   ❌ Stok habis    → Retry dari Menu")
    print("   ✅ Dapat QR      → Stop akun & notif Saved Messages")
    print("=" * 60)
    print()

    # Jalankan semua akun concurrent dengan stagger delay
    tasks = []
    for i, account in enumerate(ACCOUNTS):
        delay = i * STAGGER_DELAY  # Stagger: 0s, 2s, 4s, 6s, 8s
        task = asyncio.create_task(run_account(account, delay))
        tasks.append(task)
        print(f"   🚀 {account['name']} akan start dalam {delay}s...")

    print()

    # Tunggu semua selesai
    await asyncio.gather(*tasks)

    print()
    print("=" * 60)
    print("   SEMUA AKUN SELESAI")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
