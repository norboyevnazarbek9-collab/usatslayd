import os
import sys
import logging
import asyncio
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Reportlab va Pillow kutubxonalari importlari (hujjat/slayd generatsiya uchun)
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from PIL import Image, ImageDraw, ImageFont

# ==================== LOGGING VA CONFIG ====================
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))  # Admin telegram ID raqami

if not BOT_TOKEN:
    logger.error("BOT_TOKEN topilmadi! Render Environment Variables qismiga BOT_TOKEN ni kiriting.")
    sys.exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ==================== FSM STATES ====================
class OrderSlide(StatesGroup):
    waiting_for_topic = State()
    waiting_for_pages = State()
    waiting_for_payment = State()

# ==================== KEYBOARDS ====================
def get_main_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="📄 Slayd / Referat yaratish", callback_data="create_order")
    builder.button(text="ℹ️ Bot haqida", callback_data="about")
    builder.adjust(1)
    return builder.as_markup()

def get_payment_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 To'ladim (Tasdiqlashga yuborish)", callback_data="paid_confirm")
    builder.button(text="❌ Bekor qilish", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()

def get_admin_keyboard(user_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Tasdiqlash", callback_data=f"admin_yes_{user_id}")
    builder.button(text="❌ Rad etish", callback_data=f"admin_no_{user_id}")
    builder.adjust(2)
    return builder.as_markup()

# ==================== HANDLERS: START & MENU ====================
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        f"👋 Assalomu alaykum, **{message.from_user.full_name}**!\n\n"
        "Bu bot yordamida siz avtomatlashtirilgan tarzda taqdimot slaydlarini va referatlarni tayyorlashingiz mumkin.",
        parse_mode="Markdown",
        reply_markup=get_main_menu()
    )

@dp.callback_query(F.data == "about")
async def callback_about(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "ℹ️ **Bot imkoniyatlari:**\n\n"
        "• Avtomatik matn va slayd generatsiyasi\n"
        "• PDF va DOCX formatida yuklab olish\n"
        "• Tezkor va qulay xizmat.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardBuilder().button(text="🔙 Orqaga", callback_data="back_home").as_markup()
    )
    await callback.answer()

@dp.callback_query(F.data == "back_home")
async def callback_back(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "🏠 Asosiy menyu:",
        reply_markup=get_main_menu()
    )
    await callback.answer()

# ==================== ORDER FLOW (FSM) ====================
@dp.callback_query(F.data == "create_order")
async def start_order(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(OrderSlide.waiting_for_topic)
    await callback.message.edit_text(
        "📌 Iltimos, mavzu nomini yoki topshiriq matnini kiriting:"
    )
    await callback.answer()

@dp.message(OrderSlide.waiting_for_topic)
async def process_topic(message: types.Message, state: FSMContext):
    await state.update_data(topic=message.text)
    await state.set_state(OrderSlide.waiting_for_pages)
    await message.answer(
        "📄 Nechta varaq (yoki slayd) bo'lishi kerak? Faqat raqam kiriting (masalan: 10):"
    )

@dp.message(OrderSlide.waiting_for_pages)
async def process_pages(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Iltimos, faqat raqam kiriting (masalan: 10):")
        return
    
    pages = int(message.text)
    price = pages * 1000  # Har bir varaq uchun narx misoli
    
    await state.update_data(pages=pages, price=price)
    await state.set_state(OrderSlide.waiting_for_payment)
    
    # Narxni hisoblab ko'rsatamiz
    text = (
        f"📊 **Buyurtma ma'lumotlari:**\n\n"
        f"📌 **Mavzu:** {message.text}\n"
        f"📄 **Varoqlar soni:** {pages} ta\n"
        f"💰 **Umumiy summa:** {price} so'm\n\n"
        f"To'lovni amalga oshirish uchun karta raqam: `8600 0000 0000 0000`\n"
        f"To'lovni qilgach, pastdagi tugmani bosing."
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_payment_keyboard())

# ==================== PAYMENT CONFIRMATION ====================
@dp.callback_query(OrderSlide.waiting_for_payment, F.data == "paid_confirm")
async def process_paid_confirm(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user = callback.from_user
    
    # Python 3.11 uchun f-string tashqarisida tayyorlab olamiz (backslash xatosining oldini olish uchun)
    username = f"@{user.username}" if user.username else "Yo'q"

    await callback.message.edit_text(
        "⏳ **To'lovingiz admin tomonidan tekshirilmoqda.**\nTasdiqlanishi bilan xabar beramiz!",
        parse_mode="Markdown"
    )
    
    admin_text = (
        f"💳 **Yangi to'lov!**\n\n"
        f"👤 **Foydalanuvchi:** {user.full_name}\n"
        f"🆔 **ID:** `{user.id}`\n"
        f"🔗 **Username:** {username}\n"
        f"📌 **Mavzu:** {data.get('topic', 'Nomaʼlum')}\n"
        f"📄 **Varoqlar:** {data.get('pages', 0)} ta\n"
        f"💰 **Summa:** {data.get('price', 0)} so'm"
    )
    
    # Agar ADMIN_ID sozlangan bo'lsa, adminga xabar yuboramiz
    if ADMIN_ID:
        try:
            await bot.send_message(
                ADMIN_ID,
                admin_text,
                parse_mode="Markdown",
                reply_markup=get_admin_keyboard(user.id)
            )
        except Exception as e:
            logger.error(f"Adminga xabar yuborishda xatolik: {e}")
            
    await callback.answer("To'lov tasdiqlash uchun yuborildi!")
    await state.clear()

@dp.callback_query(F.data == "cancel")
async def cancel_order(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Buyurtma bekor qilindi.", reply_markup=get_main_menu())
    await callback.answer()

# ==================== ADMIN ACTIONS ====================
@dp.callback_query(F.data.startswith("admin_yes_"))
async def admin_approve(callback: types.CallbackQuery):
    if ADMIN_ID and callback.from_user.id != ADMIN_ID:
        await callback.answer("Bu amalni bajarishga ruxsat yo'q!", show_alert=True)
        return
        
    user_id = int(callback.data.split("_")[2])
    await callback.message.edit_text(callback.message.text + "\n\n✅ **HOLAT:** Tasdiqlandi va bajarilmoqda!", parse_mode="Markdown")
    
    try:
        await bot.send_message(user_id, "🎉 To'lovingiz tasdiqlandi! Hujjatlaringiz tayyorlanmoqda.")
    except Exception as e:
        logger.error(f"Foydalanuvchiga xabar yuborib bo'lmadi: {e}")
        
    await callback.answer("Muvaffaqiyatli tasdiqlandi!")

@dp.callback_query(F.data.startswith("admin_no_"))
async def admin_reject(callback: types.CallbackQuery):
    if ADMIN_ID and callback.from_user.id != ADMIN_ID:
        await callback.answer("Bu amalni bajarishga ruxsat yo'q!", show_alert=True)
        return
        
    user_id = int(callback.data.split("_")[2])
    await callback.message.edit_text(callback.message.text + "\n\n❌ **HOLAT:** Rad etildi.", parse_mode="Markdown")
    
    try:
        await bot.send_message(user_id, "❌ Afsuski, to'lovingiz tasdiqlanmadi yoki mablag' tushmadi. Admin bilan bog'laning.")
    except Exception as e:
        logger.error(f"Foydalanuvchiga xabar yuborib bo'lmadi: {e}")
        
    await callback.answer("Buyurtma rad etildi.")

# ==================== MAIN STARTUP ====================
async def main():
    logger.info("Bot ishga tushmoqda...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
