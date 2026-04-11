import os
import re
import glob
import logging
from typing import Optional
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp

# ========== SOZLAMALAR ==========
BOT_TOKEN = "8652149149:AAHKo1FFqXzq58KUeYyFi1yROZjvURAha54"
DOWNLOAD_DIR = "downloads"
MAX_FILE_SIZE = 50 * 1024 * 1024  # Telegram limiti 50MB

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ========== YORDAMCHI FUNKSIYALAR ==========

def detect_platform(url: str) -> Optional[str]:
    """URL qaysi platformaga tegishli ekanini aniqlash."""
    if re.search(r"(instagram\.com|instagr\.am)", url):
        return "instagram"
    elif re.search(r"(facebook\.com|fb\.watch|fb\.com)", url):
        return "facebook"
    elif re.search(r"(youtube\.com|youtu\.be|youtube\.com/shorts)", url):
        return "youtube"
    elif re.search(r"(tiktok\.com|vm\.tiktok\.com)", url):
        return "tiktok"
    return None


def clean_downloads():
    """Yuklab olingan fayllarni tozalash."""
    for f in glob.glob(os.path.join(DOWNLOAD_DIR, "*")):
        try:
            os.remove(f)
        except OSError:
            pass


def download_video(url: str, platform: str) -> Optional[str]:
    """Video yuklab olish (yt-dlp orqali)."""
    clean_downloads()

    ydl_opts = {
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title).50s.%(ext)s"),
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "postprocessors": [{
            "key": "FFmpegVideoConvertor",
            "preferedformat": "mp4",
        }],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        logger.error(f"Yuklab olishda xato: {e}")
        return None

    files = glob.glob(os.path.join(DOWNLOAD_DIR, "*"))
    if not files:
        return None

    filepath = max(files, key=os.path.getctime)

    if os.path.getsize(filepath) > MAX_FILE_SIZE:
        os.remove(filepath)
        return "KATTA"

    return filepath


def download_audio(url: str) -> Optional[str]:
    """YouTube dan audio (MP3) yuklab olish."""
    clean_downloads()

    ydl_opts = {
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title).50s.%(ext)s"),
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        logger.error(f"Audio yuklab olishda xato: {e}")
        return None

    files = glob.glob(os.path.join(DOWNLOAD_DIR, "*"))
    if not files:
        return None

    filepath = max(files, key=os.path.getctime)

    if os.path.getsize(filepath) > MAX_FILE_SIZE:
        os.remove(filepath)
        return "KATTA"

    return filepath


# ========== BOT HANDLERLARI ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 Salom! Men video yuklovchi botman.\n\n"
        "Menga quyidagi platformalardan havola yuboring:\n"
        "• YouTube (video yoki audio)\n"
        "• Instagram (reels, post)\n"
        "• Facebook (video)\n"
        "• TikTok (video)\n\n"
        "📌 YouTube havolasi bo'lsa, video yoki audio tanlash tugmalari chiqadi.\n"
        "📌 Instagram/Facebook havolasi bo'lsa, avtomatik yuklab beraman.\n\n"
        "Havola yuboring! 👇"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 Foydalanish:\n\n"
        "1. YouTube, Instagram, Facebook yoki TikTok havolasini yuboring\n"
        "2. YouTube uchun /video yoki /audio buyrug'ini ishlating\n"
        "3. Bot avtomatik yuklab beradi\n\n"
        "⚠️ Fayl hajmi 50MB dan oshmasligi kerak."
    )


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi yuborgan URLni qayta ishlash."""
    text = update.message.text.strip()

    url_match = re.search(r"https?://\S+", text)
    if not url_match:
        return

    url = url_match.group(0)
    platform = detect_platform(url)

    if not platform:
        await update.message.reply_text(
            "❌ Bu havola qo'llab-quvvatlanmaydi.\n"
            "Faqat YouTube, Instagram va Facebook havolalari ishlaydi."
        )
        return

    if platform == "youtube":
        context.user_data["last_url"] = url
        await update.message.reply_text(
            "🎬 YouTube havolasi aniqlandi!\n\n"
            "Nima yuklab olmoqchisiz?\n"
            "• /video — Video yuklab olish\n"
            "• /audio — Audio (MP3) yuklab olish"
        )
        return

    # Instagram, Facebook va TikTok uchun avtomatik video yuklash
    platform_names = {"instagram": "Instagram", "facebook": "Facebook", "tiktok": "TikTok"}
    platform_name = platform_names[platform]
    msg = await update.message.reply_text(f"⏳ {platform_name} dan yuklab olinmoqda...")

    filepath = download_video(url, platform)

    if filepath is None:
        await msg.edit_text(
            f"❌ {platform_name} dan yuklab bo'lmadi.\n"
            "Havola to'g'ri ekanini tekshiring."
        )
        return

    if filepath == "KATTA":
        await msg.edit_text("❌ Fayl hajmi 50MB dan katta. Telegram limiti.")
        return

    try:
        await msg.edit_text(f"📤 {platform_name} — Yuborilmoqda...")
        with open(filepath, "rb") as f:
            await update.message.reply_video(
                video=f,
                caption=f"✅ {platform_name} dan yuklandi | @vidomaxbot"
            )
        await msg.delete()
    except Exception as e:
        logger.error(f"Yuborishda xato: {e}")
        await msg.edit_text("❌ Faylni yuborishda xatolik yuz berdi.")
    finally:
        clean_downloads()


async def video_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """YouTube dan video yuklab olish."""
    url = context.user_data.get("last_url")
    if not url:
        await update.message.reply_text(
            "❌ Avval YouTube havolasini yuboring!"
        )
        return

    msg = await update.message.reply_text("⏳ YouTube video yuklab olinmoqda...")

    filepath = download_video(url, "youtube")
    context.user_data.pop("last_url", None)

    if filepath is None:
        await msg.edit_text("❌ Videoni yuklab bo'lmadi. Havola to'g'ri ekanini tekshiring.")
        return

    if filepath == "KATTA":
        await msg.edit_text("❌ Video hajmi 50MB dan katta. Telegram limiti.")
        return

    try:
        await msg.edit_text("📤 Video yuborilmoqda...")
        with open(filepath, "rb") as f:
            await update.message.reply_video(
                video=f,
                caption="✅ YouTube dan yuklandi | @vidomaxbot"
            )
        await msg.delete()
    except Exception as e:
        logger.error(f"Yuborishda xato: {e}")
        await msg.edit_text("❌ Videoni yuborishda xatolik yuz berdi.")
    finally:
        clean_downloads()


async def audio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """YouTube dan audio (MP3) yuklab olish."""
    url = context.user_data.get("last_url")
    if not url:
        await update.message.reply_text(
            "❌ Avval YouTube havolasini yuboring!"
        )
        return

    msg = await update.message.reply_text("⏳ YouTube audio yuklab olinmoqda...")

    filepath = download_audio(url)
    context.user_data.pop("last_url", None)

    if filepath is None:
        await msg.edit_text("❌ Audioni yuklab bo'lmadi. Havola to'g'ri ekanini tekshiring.")
        return

    if filepath == "KATTA":
        await msg.edit_text("❌ Audio hajmi 50MB dan katta. Telegram limiti.")
        return

    try:
        await msg.edit_text("📤 Audio yuborilmoqda...")
        with open(filepath, "rb") as f:
            await update.message.reply_audio(
                audio=f,
                caption="🎵 YouTube dan yuklandi | @vidomaxbot"
            )
        await msg.delete()
    except Exception as e:
        logger.error(f"Yuborishda xato: {e}")
        await msg.edit_text("❌ Audioni yuborishda xatolik yuz berdi.")
    finally:
        clean_downloads()


# ========== ASOSIY FUNKSIYA ==========

def main():
    if not BOT_TOKEN or BOT_TOKEN == "BOT_TOKENINGIZNI_SHU_YERGA_YOZING":
        print("❌ BOT_TOKEN ni o'zgartiring! @BotFather dan token oling.")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("video", video_command))
    app.add_handler(CommandHandler("audio", audio_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))

    print("✅ Bot ishga tushdi!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
